"""Policy and contract tests for the discord-hub adapter.

Authorization gating stays in Socrates (ADR 0003), so the boundary
permutations here are the load-bearing evidence that private input cannot
cross the allowlist through the new transport.
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from pathlib import Path

import pytest

from socratic_partner.application import AgentRequestFailed
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
from socratic_partner.hub_client import HubError
from socratic_partner.pi_rpc import PiRpcError, PiRunResult
from socratic_partner.store import ConversationStatus, StateStore

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
    test_database_path=Path("data/test.testing.sqlite3"),
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
    assert hub.registration["allow_thread_deletion"] is True


def test_model_option_declares_hub_autocomplete(tmp_path) -> None:
    """Autocomplete must be declared or Discord will never route typing to us."""
    adapter = _adapter(tmp_path, SETTINGS)

    model_command = next(
        command for command in adapter._command_declarations() if command["name"] == "model"
    )

    assert model_command["options"][0]["autocomplete"] is True


async def test_failed_ask_now_deletes_the_empty_thread(tmp_path) -> None:
    """A paid/model failure must not leave a Discord thread that looks like a session."""
    hub = _FakeHub()
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=3600)
    store.initialize()
    adapter = SocraticHubAdapter(
        SETTINGS, store, _ScriptedPi([PiRpcError("provider unavailable")]), hub
    )

    text = await adapter._deferred_ask_now(_command_payload("ask-now"))

    assert hub.deleted_threads == [111]
    assert store.get_active_conversation() is None
    assert "no answer was accepted" in text.lower()


async def test_delivery_failure_after_thread_creation_deletes_the_thread(tmp_path) -> None:
    """Cleanup belongs at the adapter boundary where the otherwise-orphaned thread exists."""
    hub = _FakeHub()
    hub.fail_next_post = True
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=3600)
    store.initialize()
    adapter = SocraticHubAdapter(SETTINGS, store, _ScriptedPi(["Opening question?"]), hub)

    text = await adapter._deferred_ask_now(_command_payload("ask-now"))

    assert hub.deleted_threads == [111]
    assert store.get_active_conversation() is None
    assert "could not be delivered" in text


async def test_persistence_failure_after_thread_creation_deletes_the_thread(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SQLite failure must not leave Discord claiming a conversation exists when none was saved."""
    hub = _FakeHub()
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=3600)
    store.initialize()

    def fail_start_conversation(**kwargs: object) -> None:
        raise RuntimeError("database closed")

    monkeypatch.setattr(store, "start_conversation", fail_start_conversation)
    adapter = SocraticHubAdapter(SETTINGS, store, _ScriptedPi(["Opening question?"]), hub)

    text = await adapter._deferred_ask_now(_command_payload("ask-now"))

    assert hub.deleted_threads == [111]
    assert "could not be delivered or saved" in text


async def test_thread_creation_failure_has_no_thread_to_delete(tmp_path) -> None:
    """Cleanup must not invent an ID when the hub never created Discord state."""
    hub = _FakeHub()
    hub.create_thread_error = HubError("Discord rejected thread creation", status_code=502)
    adapter = SocraticHubAdapter(SETTINGS, _adapter_store(tmp_path), _ScriptedPi([]), hub)

    text = await adapter._deferred_ask_now(_command_payload("ask-now"))

    assert hub.deleted_threads == []
    assert "could not be delivered or saved" in text


async def test_successful_ask_now_keeps_the_session_thread(tmp_path) -> None:
    """Cleanup is only for startup failure; a real opening remains visible in its thread."""
    hub = _FakeHub()
    store = _adapter_store(tmp_path)
    adapter = SocraticHubAdapter(SETTINGS, store, _ScriptedPi(["Opening question?"]), hub)

    text = await adapter._deferred_ask_now(_command_payload("ask-now"))

    assert hub.deleted_threads == []
    assert store.get_active_conversation() is not None
    assert "conversation is open" in text


async def test_failed_automatic_kickoff_also_deletes_the_empty_thread(tmp_path) -> None:
    """Automatic and manual starts share the thread-creation risk and cleanup guarantee."""
    hub = _FakeHub()
    store = _adapter_store(tmp_path)
    adapter = SocraticHubAdapter(
        SETTINGS, store, _ScriptedPi([PiRpcError("provider unavailable")]), hub
    )
    lease = adapter.operation_gate.try_acquire("automatic kickoff")
    assert lease is not None

    with pytest.raises(AgentRequestFailed):
        async with lease:
            await adapter._automatic_kickoff(lease)

    assert hub.deleted_threads == [111]
    assert store.get_active_conversation() is None


async def test_start_reregisters_existing_channel_to_allow_thread_deletion(tmp_path) -> None:
    """The deployed reflection registration predates the hub opt-in and must be upgraded."""
    hub = _FakeHub()
    hub.registrations = [{"channel_id": "200", "allow_thread_deletion": False}]
    adapter = SocraticHubAdapter(SETTINGS, _adapter_store(tmp_path), _FakePi(), hub)

    await adapter.start()

    assert hub.deregistered_channels == [200]
    assert hub.registration is not None
    assert hub.registration["allow_thread_deletion"] is True


async def test_done_archives_the_completed_thread(tmp_path) -> None:
    """A completed session should leave the active channel without losing its record."""
    hub = _FakeHub()
    store = _adapter_store(tmp_path)
    adapter = SocraticHubAdapter(
        SETTINGS, store, _ScriptedPi(["Opening question?", "Session card"]), hub
    )
    await adapter._deferred_ask_now(_command_payload("ask-now"))
    conversation = store.get_active_conversation()
    assert conversation is not None

    text = await adapter._deferred_done(
        _command_payload("done", channel_id=str(conversation.channel_id))
    )

    assert hub.archived_threads == [(conversation.channel_id, True, False)]
    assert store.get_conversation(conversation.id).status is ConversationStatus.COMPLETED
    assert "Conversation closed" in text


async def test_archive_failure_does_not_reopen_completed_conversation(tmp_path) -> None:
    """Discord cleanup is important but must not corrupt the durable completion boundary."""
    hub = _FakeHub()
    hub.archive_thread_error = HubError("Discord archive failed", status_code=502)
    store = _adapter_store(tmp_path)
    adapter = SocraticHubAdapter(
        SETTINGS, store, _ScriptedPi(["Opening question?", "Session card"]), hub
    )
    await adapter._deferred_ask_now(_command_payload("ask-now"))
    conversation = store.get_active_conversation()
    assert conversation is not None

    text = await adapter._deferred_done(
        _command_payload("done", channel_id=str(conversation.channel_id))
    )

    assert store.get_conversation(conversation.id).status is ConversationStatus.COMPLETED
    assert "closed" in text.lower() and "archive" in text.lower()


async def test_failed_done_does_not_archive_the_thread(tmp_path) -> None:
    """Only a successful completion may tidy the thread away from the active channel."""
    hub = _FakeHub()
    store = _adapter_store(tmp_path)
    adapter = SocraticHubAdapter(
        SETTINGS,
        store,
        _ScriptedPi(["Opening question?", PiRpcError("provider unavailable")]),
        hub,
    )
    await adapter._deferred_ask_now(_command_payload("ask-now"))
    conversation = store.get_active_conversation()
    assert conversation is not None

    text = await adapter._deferred_done(
        _command_payload("done", channel_id=str(conversation.channel_id))
    )

    assert hub.archived_threads == []
    assert store.get_active_conversation() is not None
    assert "remains open" in text


async def test_model_autocomplete_filters_available_models(tmp_path) -> None:
    """Autocomplete should turn Pi's model inventory into Discord's bounded choice shape."""
    adapter = SocraticHubAdapter(SETTINGS, _adapter_store(tmp_path), _ScriptedPi([]), _FakeHub())

    response = await adapter.dispatch(_autocomplete_payload("gpt"))

    assert response == {
        "choices": [{"name": "openai/gpt-5 — GPT-5", "value": "openai/gpt-5"}]
    }


async def test_model_autocomplete_limits_choices_and_survives_pi_failure(tmp_path) -> None:
    """Discord accepts at most 25 choices and autocomplete must never leave the UI hanging."""
    pi = _ScriptedPi([])
    pi.models = [
        {"provider": "test", "id": f"model-{index:02d}", "name": f"Model {index:02d}"}
        for index in range(30)
    ]
    adapter = SocraticHubAdapter(SETTINGS, _adapter_store(tmp_path), pi, _FakeHub())

    response = await adapter.dispatch(_autocomplete_payload("model"))
    assert response is not None
    assert len(response["choices"]) == 25

    class FailingPi(_FakePi):
        async def get_available_models(self) -> list[dict]:
            raise PiRpcError("Pi unavailable")

    adapter = SocraticHubAdapter(SETTINGS, _adapter_store(tmp_path), FailingPi(), _FakeHub())
    assert await adapter.dispatch(_autocomplete_payload("anything")) == {"choices": []}


async def test_model_autocomplete_obeys_authorization(tmp_path) -> None:
    """The autocomplete route is a command surface and gets the same allowlist policy."""
    adapter = SocraticHubAdapter(SETTINGS, _adapter_store(tmp_path), _ScriptedPi([]), _FakeHub())

    assert await adapter.dispatch(_autocomplete_payload("gpt", user_id="301")) == {
        "choices": []
    }
    assert await adapter.dispatch(_autocomplete_payload("gpt", channel_id="201")) == {
        "choices": []
    }


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


def _command_payload(
    command: str,
    options: dict | None = None,
    *,
    channel_id: str = "200",
    user_id: str = "300",
) -> dict:
    return {
        "type": "command",
        "interaction_id": "1",
        "command": command,
        "options": options or {},
        "channel_id": channel_id,
        "user": {"id": user_id, "name": "owner"},
    }


def _autocomplete_payload(
    value: str,
    *,
    channel_id: str = "200",
    user_id: str = "300",
) -> dict:
    return {
        "type": "autocomplete",
        "command": "model",
        "option": {"name": "model", "value": value},
        "options": {"model": value},
        "channel_id": channel_id,
        "user": {"id": user_id, "name": "owner"},
    }


def _adapter_store(tmp_path: Path) -> StateStore:
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=3600)
    store.initialize()
    return store


class _FakeHub:
    """Protocol-shaped hub substitute; records calls, answers minimally."""

    def __init__(self) -> None:
        self.posted: list[tuple[int, str]] = []
        self.commands: list[dict] | None = None
        self.registration: dict | None = None
        self.registrations: list[dict] = []
        self.deregistered_channels: list[int] = []
        self.deleted_threads: list[int] = []
        self.archived_threads: list[tuple[int, bool, bool]] = []
        self.delete_thread_error: HubError | None = None
        self.archive_thread_error: HubError | None = None
        self.create_thread_error: HubError | None = None
        self.fail_next_post = False

    async def health(self) -> dict:
        return {"status": "ok", "discord_connected": True}

    async def post_message(self, channel_id: int, text: str, **kwargs: object) -> dict:
        if self.fail_next_post:
            self.fail_next_post = False
            raise HubError("simulated delivery failure")
        self.posted.append((channel_id, text))
        self.post_kwargs = kwargs
        return {"id": "1", "channel_id": str(channel_id)}

    async def create_thread(self, channel_id: int, name: str) -> dict:
        if self.create_thread_error is not None:
            raise self.create_thread_error
        return {"id": "111", "name": name, "parent_channel_id": str(channel_id)}

    async def get_registrations(self) -> list[dict]:
        return self.registrations

    async def deregister_channel(self, channel_id: int) -> None:
        self.deregistered_channels.append(channel_id)

    async def delete_thread(self, thread_id: int) -> None:
        if self.delete_thread_error is not None:
            raise self.delete_thread_error
        self.deleted_threads.append(thread_id)

    async def archive_thread(
        self, thread_id: int, *, archived: bool = True, locked: bool = False
    ) -> dict:
        if self.archive_thread_error is not None:
            raise self.archive_thread_error
        self.archived_threads.append((thread_id, archived, locked))
        return {"id": str(thread_id), "archived": archived, "locked": locked}

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
        return [
            "view_channel",
            "send_messages",
            "read_message_history",
            "create_public_threads",
            "send_messages_in_threads",
        ]

    async def close(self) -> None:
        return None


class _FakePi:
    is_running = False

    async def close(self) -> None:
        return None


class _ScriptedPi(_FakePi):
    """Protocol-shaped Pi substitute for adapter workflows across real SQLite."""

    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = deque(responses)
        self.new_session_count = 0
        self.prompt_count = 0
        self.models = [
            {"provider": "openai", "id": "gpt-5", "name": "GPT-5"},
            {"provider": "anthropic", "id": "claude-sonnet-4", "name": "Claude Sonnet 4"},
        ]

    async def new_session(self) -> dict[str, object]:
        self.new_session_count += 1
        return {"sessionId": f"session-{self.new_session_count}"}

    async def prompt(self, message: str) -> PiRunResult:
        self.prompt_count += 1
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return PiRunResult(
            text=response,
            session_id=f"session-{self.new_session_count}",
            session_file=None,
            provider="test-provider",
            model_id="test-model",
            input_tokens=1,
            output_tokens=1,
            cost=0.0,
        )

    async def get_available_models(self) -> list[dict]:
        return self.models


def _adapter(tmp_path: Path, settings: Settings) -> SocraticHubAdapter:
    return SocraticHubAdapter(settings, _adapter_store(tmp_path), _FakePi(), _FakeHub())


# -- /testing toggle and /delete-session ------------------------------------


def _testing_settings(tmp_path: Path, **overrides) -> Settings:
    return replace(
        SETTINGS,
        test_controls_enabled=True,
        test_database_path=tmp_path / "testing.sqlite3",
        **overrides,
    )


def test_testing_and_delete_session_commands_are_always_available(tmp_path) -> None:
    """Both cleanup controls must stay reachable without a restart: `/testing`
    taints nothing (isolated store, reversible, refused mid-conversation), and
    an accidental live-DB test is exactly when `/delete-session` is needed.
    Only `/test-interval`, which rewires the live automation rhythm, stays
    gated behind test controls."""
    adapter = _adapter(tmp_path, SETTINGS)
    names = {c["name"] for c in adapter._command_declarations()}
    assert "testing" in names
    assert "delete-session" in names
    assert "test-interval" not in names


async def test_testing_toggle_swaps_store_and_restores_live_state(tmp_path) -> None:
    """The live store must be untouched and resumed exactly as left.

    This is the feature's core promise: test data can never taint live data,
    because the two never share a database file.
    """
    adapter = _adapter(tmp_path, _testing_settings(tmp_path))
    live_store = adapter.store

    response = await adapter._immediate_testing(_command_payload("testing", {"enabled": True}))
    assert adapter.testing_active
    assert adapter.store is not live_store
    assert adapter.store.database_path != live_store.database_path
    assert "test" in response["text"]

    adapter.store.pause()  # dirty the test store only

    response = await adapter._immediate_testing(_command_payload("testing", {"enabled": False}))
    assert not adapter.testing_active
    assert adapter.store is live_store
    assert live_store.get_state().status.value == "WAITING"


async def test_testing_toggle_refused_while_conversation_open(tmp_path) -> None:
    """The Pi session is shared; swapping mid-conversation would cross-contaminate
    the sessions each store has recorded."""
    adapter = _adapter(tmp_path, _testing_settings(tmp_path))
    adapter.store.start_conversation(
        conversation_id="c1", channel_id=111, question_message_id=1
    )

    response = await adapter._immediate_testing(_command_payload("testing", {"enabled": True}))

    assert not adapter.testing_active
    assert "open" in response["text"]


async def test_delete_session_from_home_channel_discards_and_deletes_thread(tmp_path) -> None:
    """Black-box path for the common case: the user cleans up from the home
    channel; local state goes and the hub is asked to delete the thread."""
    hub = _FakeHub()
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=3600)
    store.initialize()
    store.start_conversation(conversation_id="c1", channel_id=111, question_message_id=1)
    adapter = SocraticHubAdapter(SETTINGS, store, _FakePi(), hub)

    text = await adapter._deferred_delete_session(_command_payload("delete-session"))

    assert store.get_active_conversation() is None
    assert store.get_conversation("c1") is None
    assert hub.deleted_threads == [111]
    assert "deleted" in text


async def test_delete_session_degrades_when_hub_lacks_thread_deletion(tmp_path) -> None:
    """Until the hub ships the deletion primitive, local cleanup must still
    succeed and the reply must say the thread needs manual deletion."""
    hub = _FakeHub()
    hub.delete_thread_error = HubError("not found", status_code=404)
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=3600)
    store.initialize()
    store.start_conversation(conversation_id="c1", channel_id=111, question_message_id=1)
    adapter = SocraticHubAdapter(SETTINGS, store, _FakePi(), hub)

    text = await adapter._deferred_delete_session(_command_payload("delete-session"))

    assert store.get_conversation("c1") is None
    assert "manually" in text


async def test_delete_session_without_conversation_says_so(tmp_path) -> None:
    adapter = _adapter(tmp_path, SETTINGS)

    text = await adapter._deferred_delete_session(_command_payload("delete-session"))

    assert "no conversation" in text
