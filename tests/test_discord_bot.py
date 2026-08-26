"""Authorization boundary permutations share one risk: private input crossing its allowlist."""

from pathlib import Path

import pytest

from socratic_partner.config import Settings
from socratic_partner.discord_bot import _defer_then_acquire, is_authorized
from socratic_partner.operation_gate import OperationGate

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
