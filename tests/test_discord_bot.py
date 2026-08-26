"""Authorization boundary permutations share one risk: private input crossing its allowlist."""

import asyncio
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from discord.ext import commands

from socratic_partner.config import Settings
from socratic_partner.discord_bot import (
    SocraticPartnerBot,
    _defer_then_acquire,
    _format_scheduler_status,
    is_authorized,
)
from socratic_partner.errors import ClassifiedError, ErrorKind
from socratic_partner.operation_gate import OperationGate
from socratic_partner.store import StateStore

SETTINGS = Settings(
    discord_bot_token="test-token",
    discord_guild_id=100,
    discord_test_channel_id=200,
    discord_allowed_user_id=300,
    test_mode=True,
    log_level="INFO",
    database_path=Path("data/test.sqlite3"),
    default_interval_seconds=24 * 60 * 60,
    pi_executable="pi",
    pi_session_directory=Path("data/pi-sessions"),
    pi_model=None,
    pi_timeout_seconds=120,
    automatic_scheduler_enabled=False,
)


def test_authorizes_exact_development_boundary() -> None:
    assert is_authorized(SETTINGS, guild_id=100, channel_id=200, user_id=300)


def test_rejects_wrong_guild() -> None:
    assert not is_authorized(SETTINGS, guild_id=101, channel_id=200, user_id=300)


def test_rejects_wrong_channel() -> None:
    assert not is_authorized(SETTINGS, guild_id=100, channel_id=201, user_id=300)


def test_rejects_wrong_user() -> None:
    assert not is_authorized(SETTINGS, guild_id=100, channel_id=200, user_id=301)


def test_rejects_direct_message() -> None:
    assert not is_authorized(SETTINGS, guild_id=None, channel_id=200, user_id=300)


class FakePiClient:
    def __init__(self, events: list[str] | None = None) -> None:
        self.events = events
        self.is_running = False

    async def close(self) -> None:
        if self.events is not None:
            self.events.append("pi_closed")


def make_bot(tmp_path, *, scheduler_enabled: bool) -> SocraticPartnerBot:
    settings = replace(
        SETTINGS,
        database_path=tmp_path / "state.sqlite3",
        automatic_scheduler_enabled=scheduler_enabled,
    )
    store = StateStore(settings.database_path, default_interval_seconds=86_400)
    store.initialize()
    return SocraticPartnerBot(settings, store, FakePiClient())


async def test_failed_command_acknowledgement_does_not_claim_operation_gate() -> None:
    """A Discord acknowledgement failure must occur before acquisition so no lease is stranded."""

    class FailingResponse:
        async def defer(self, *, ephemeral: bool, thinking: bool) -> None:
            raise RuntimeError("simulated acknowledgement failure")

    class UnexpectedFollowup:
        async def send(self, message: str, *, ephemeral: bool) -> None:
            raise AssertionError("followup must not run when acknowledgement fails")

    class Interaction:
        response = FailingResponse()
        followup = UnexpectedFollowup()

    gate = OperationGate()

    with pytest.raises(RuntimeError, match="simulated acknowledgement failure"):
        await _defer_then_acquire(
            Interaction(), gate, operation="running a Pi connectivity test"
        )

    assert gate.current_operation is None


async def test_flag_off_and_repeated_ready_control_scheduler_task_count(tmp_path) -> None:
    """Disabled deployments create no task; reconnect-ready events must not duplicate one."""
    disabled = make_bot(tmp_path / "disabled", scheduler_enabled=False)
    await disabled.on_ready()
    assert disabled._scheduler_task is None

    enabled = make_bot(tmp_path / "enabled", scheduler_enabled=True)
    never_wake = asyncio.Event()

    async def controlled_sleep(seconds: float) -> None:
        assert seconds <= 60
        await never_wake.wait()

    enabled._scheduler_sleep = controlled_sleep
    await enabled.on_ready()
    first_task = enabled._scheduler_task
    await enabled.on_ready()

    assert first_task is not None
    assert enabled._scheduler_task is first_task
    first_task.cancel()
    with suppress(asyncio.CancelledError):
        await first_task


async def test_shutdown_awaits_scheduler_before_pi_and_discord_close(
    tmp_path, monkeypatch
) -> None:
    """Shutdown ordering prevents new background work after Pi teardown begins."""
    events: list[str] = []
    bot = make_bot(tmp_path, scheduler_enabled=True)
    bot.pi_client = FakePiClient(events)

    async def running_scheduler() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            events.append("scheduler_stopped")

    async def fake_discord_close(self) -> None:
        events.append("discord_closed")

    monkeypatch.setattr(commands.Bot, "close", fake_discord_close)
    bot._scheduler_task = asyncio.create_task(running_scheduler())
    await asyncio.sleep(0)

    await bot.close()

    assert events == ["scheduler_stopped", "pi_closed", "discord_closed"]
    assert bot._scheduler_stopping is True


def test_scheduler_status_formats_only_observed_runtime_state() -> None:
    """Status distinguishes configuration, active work, and retry time without diagnosis."""
    gate = OperationGate()
    disabled = SimpleNamespace(scheduler=None, operation_gate=gate)
    scheduler = SimpleNamespace(retry_at=None)
    enabled = SimpleNamespace(scheduler=scheduler, operation_gate=gate)

    assert _format_scheduler_status(disabled) == "disabled"
    assert _format_scheduler_status(enabled) == "enabled-idle"

    scheduler.retry_at = datetime(2026, 8, 28, tzinfo=UTC)
    assert "retry at 2026-08-28T00:00:00+00:00" in _format_scheduler_status(enabled)

    lease = gate.try_acquire("automatic kickoff")
    assert lease is not None
    assert _format_scheduler_status(enabled) == "running"
    lease.release()


@pytest.mark.parametrize("delivery_fails", [False, True])
async def test_automatic_failure_notification_is_a_single_persistent_send(
    tmp_path, delivery_fails: bool
) -> None:
    """Composition attempts one safe channel message and leaves best-effort handling to policy."""
    bot = make_bot(tmp_path, scheduler_enabled=True)
    sent: list[tuple[int, str]] = []

    class Messenger:
        async def send(self, channel_id: int, text: str) -> int:
            sent.append((channel_id, text))
            if delivery_fails:
                raise RuntimeError("simulated Discord failure")
            return 1

    bot._messenger = Messenger()
    failure = ClassifiedError(ErrorKind.BILLING, "raw provider detail")

    if delivery_fails:
        with pytest.raises(RuntimeError, match="simulated Discord failure"):
            await bot._notify_automatic_failure(failure)
    else:
        await bot._notify_automatic_failure(failure)

    assert len(sent) == 1
    assert sent[0][0] == SETTINGS.discord_test_channel_id
    assert "raw provider detail" not in sent[0][1]
