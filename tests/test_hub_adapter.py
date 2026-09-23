"""Policy and contract tests for the discord-hub adapter.

Authorization gating stays in Socrates (ADR 0003), so the boundary
permutations here are the load-bearing evidence that private input cannot
cross the allowlist through the new transport.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from socratic_partner.config import Settings
from socratic_partner.hub_adapter import (
    HubConversationMessenger,
    InboundMessage,
    SocraticHubAdapter,
    _format_interval,
    _format_scheduler_configuration,
    _format_scheduler_status,
    _session_thread_name,
    command_authorized,
    message_authorized,
)
from socratic_partner.store import StateStore

SETTINGS = Settings(
    discord_channel_id=200,
    discord_allowed_user_id=300,
    hub_url="http://localhost:8100",
    callback_host="127.0.0.1",
    callback_port=9100,
    callback_url="http://localhost:9100/discord",
    avatar_url=None,
    test_mode=True,
    test_controls_enabled=False,
    log_level="INFO",
    database_path=Path("data/test.sqlite3"),
    default_interval_seconds=24 * 60 * 60,
    pi_executable="pi",
    pi_session_directory=Path("data/pi-sessions"),
    pi_model=None,
    pi_timeout_seconds=120,
    automatic_scheduler_enabled=False,
)


def test_authorizes_message_in_home_channel() -> None:
    assert message_authorized(SETTINGS, channel_id=200, user_id=300)


def test_authorizes_message_in_session_thread_through_parent() -> None:
    """Sessions live in threads; a thread's own ID is never the configured channel."""
    assert message_authorized(SETTINGS, channel_id=999, user_id=300, parent_channel_id=200)


def test_rejects_message_in_thread_of_unrelated_channel() -> None:
    assert not message_authorized(
        SETTINGS, channel_id=999, user_id=300, parent_channel_id=201
    )


def test_rejects_message_from_wrong_user() -> None:
    assert not message_authorized(SETTINGS, channel_id=200, user_id=301)


def test_rejects_message_when_test_mode_off() -> None:
    settings = replace(SETTINGS, test_mode=False)
    assert not message_authorized(settings, channel_id=200, user_id=300)


def test_authorizes_command_in_home_channel() -> None:
    assert command_authorized(
        SETTINGS, channel_id=200, user_id=300, active_conversation_channel_id=None
    )


def test_authorizes_command_in_the_active_session_thread() -> None:
    """`/done` runs inside the session thread; the hub payload has no parent field,
    so the thread is recognized as the active conversation's channel."""
    assert command_authorized(
        SETTINGS, channel_id=999, user_id=300, active_conversation_channel_id=999
    )


def test_rejects_command_in_an_inactive_thread() -> None:
    """A stale archived thread must not become a control surface."""
    assert not command_authorized(
        SETTINGS, channel_id=999, user_id=300, active_conversation_channel_id=555
    )


def test_rejects_command_from_wrong_user() -> None:
    assert not command_authorized(
        SETTINGS, channel_id=200, user_id=301, active_conversation_channel_id=None
    )


def test_short_interval_declaration_requires_explicit_gate(tmp_path) -> None:
    """The short-interval test control must not appear in the published command
    set unless test controls are explicitly enabled."""
    adapter = _adapter(tmp_path, SETTINGS)
    assert "test-interval" not in {c["name"] for c in adapter._command_declarations()}

    gated = replace(SETTINGS, test_controls_enabled=True)
    adapter = _adapter(tmp_path, gated)
    assert "test-interval" in {c["name"] for c in adapter._command_declarations()}


async def test_dispatch_rejects_unauthorized_command_with_generic_response(
    tmp_path,
) -> None:
    """Rejection reveals nothing about the deployment boundary."""
    adapter = _adapter(tmp_path, SETTINGS)

    response = await adapter.dispatch(
        {
            "type": "command",
            "interaction_id": "1",
            "command": "status",
            "options": {},
            "channel_id": "200",
            "user": {"id": "301", "name": "intruder"},
        }
    )

    assert response == {
        "text": "This development command is not available here.",
        "ephemeral": True,
    }


async def test_dispatch_defers_long_commands_and_answers_immediate_ones(tmp_path) -> None:
    """The hub turns the HTTP response into the interaction response; long model
    work must defer within Discord's ~3 second window."""
    adapter = _adapter(tmp_path, SETTINGS)

    deferred = await adapter.dispatch(_command_payload("ask-now"))
    assert deferred == {"defer": True, "ephemeral": True}

    immediate = await adapter.dispatch(_command_payload("status"))
    assert immediate["ephemeral"] is True
    assert "Socratic Partner" in immediate["text"]


async def test_unknown_command_is_rejected(tmp_path) -> None:
    adapter = _adapter(tmp_path, SETTINGS)
    response = await adapter.dispatch(_command_payload("explode"))
    assert response == {"text": "Unknown command.", "ephemeral": True}


def test_session_thread_names_are_timestamped() -> None:
    """Thread titles are stable and sortable until LLM titles are chosen."""
    from datetime import UTC, datetime

    name = _session_thread_name(datetime(2026, 9, 6, 14, 30, tzinfo=UTC))
    assert name == "Session 2026-09-06 14:30 UTC"


def test_interval_status_makes_short_test_timing_explicit() -> None:
    """The status output must distinguish minutes from hours for supervised tests."""
    assert _format_interval(60) == "1 minute"
    assert _format_interval(3600) == "1 hour"
    assert _format_interval(7200) == "2 hours"


def test_resume_reports_scheduler_configuration_without_stale_claims() -> None:
    assert _format_scheduler_configuration(SETTINGS) == (
        "Automatic scheduler configuration is **disabled** until restart."
    )


async def test_scheduler_loop_stops_promptly_on_close(tmp_path) -> None:
    """Regression: Ctrl+C must not stall 30s on the scheduler's 60s sleep.

    Observed live: the harness hit its shutdown timeout and force-cancelled
    because the loop slept through the stop signal.
    """
    import asyncio

    enabled = replace(SETTINGS, automatic_scheduler_enabled=True)
    adapter = _adapter(tmp_path, enabled)
    task = asyncio.create_task(adapter.run_scheduler())
    await asyncio.sleep(0)  # let the first tick happen
    await adapter.close()
    await asyncio.wait_for(task, timeout=5)
    assert task.done()


def test_scheduler_status_formats_only_observed_runtime_state(tmp_path) -> None:
    """Status must not invent a scheduler that configuration did not enable."""
    adapter = _adapter(tmp_path, SETTINGS)
    assert _format_scheduler_status(adapter) == "disabled"


async def test_start_registers_identity_with_avatar(tmp_path) -> None:
    """The webhook identity (ADR 0002) carries the configured name and avatar;
    a missing avatar must register as absent, not as an empty string."""
    hub = _FakeHub()
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=3600)
    store.initialize()
    settings = replace(SETTINGS, avatar_url="https://example.test/socrates.png")
    adapter = SocraticHubAdapter(settings, store, _FakePi(), hub)

    await adapter.start()

    assert hub.registration is not None
    assert hub.registration["display_name"] == "Socrates"
    assert hub.registration["avatar_url"] == "https://example.test/socrates.png"


async def test_conversation_replies_do_not_use_reply_reference(tmp_path) -> None:
    """Replies must keep the Socrates webhook identity.

    reply_to_message_id forces the hub's plain bot path (webhooks cannot
    reply), which stripped the identity in live testing; the session thread
    already supplies the context a reply reference would.
    """
    hub = _FakeHub()
    messenger = HubConversationMessenger(hub)
    reference = InboundMessage(message_id="42", channel_id=999, text="hi")

    await messenger.reply(reference, "an answer")

    assert hub.posted == [(999, "an answer")]
    assert "reply_to_message_id" not in hub.post_kwargs


# -- fixtures ---------------------------------------------------------------


def _command_payload(command: str, options: dict | None = None) -> dict:
    return {
        "type": "command",
        "interaction_id": "1",
        "command": command,
        "options": options or {},
        "channel_id": "200",
        "user": {"id": "300", "name": "owner"},
    }


class _FakeHub:
    """Protocol-shaped hub substitute; records calls, answers minimally."""

    def __init__(self) -> None:
        self.posted: list[tuple[int, str]] = []
        self.commands: list[dict] | None = None
        self.registration: dict | None = None

    async def health(self) -> dict:
        return {"status": "ok", "discord_connected": True}

    async def post_message(self, channel_id: int, text: str, **kwargs: object) -> dict:
        self.posted.append((channel_id, text))
        self.post_kwargs = kwargs
        return {"id": "1", "channel_id": str(channel_id)}

    async def create_thread(self, channel_id: int, name: str) -> dict:
        return {"id": "111", "name": name, "parent_channel_id": str(channel_id)}

    async def get_registrations(self) -> list[dict]:
        return []

    async def register_channel(self, channel_id: int, callback_url: str, **kw: object) -> dict:
        self.registration = {"channel_id": channel_id, "callback_url": callback_url, **kw}
        return {"channel_id": str(channel_id), "callback_url": callback_url}

    async def put_commands(self, callback_url: str, commands: list[dict]) -> dict:
        self.commands = commands
        return {"synced": len(commands)}

    async def post_followup(self, interaction_id: str, text: str, **kw: object) -> dict:
        return {}

    async def typing(self, channel_id: int) -> None:
        return None

    async def channel_permissions(self, channel_id: int) -> list[str]:
        return []

    async def close(self) -> None:
        return None


class _FakePi:
    is_running = False

    async def close(self) -> None:
        return None


def _adapter(tmp_path: Path, settings: Settings) -> SocraticHubAdapter:
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=3600)
    store.initialize()
    return SocraticHubAdapter(settings, store, _FakePi(), _FakeHub())
