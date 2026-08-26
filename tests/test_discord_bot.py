from pathlib import Path

from socratic_partner.config import Settings
from socratic_partner.discord_bot import is_authorized

SETTINGS = Settings(
    discord_bot_token="test-token",
    discord_guild_id=100,
    discord_test_channel_id=200,
    discord_allowed_user_id=300,
    test_mode=True,
    log_level="INFO",
    database_path=Path("data/test.sqlite3"),
    default_interval_seconds=24 * 60 * 60,
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
