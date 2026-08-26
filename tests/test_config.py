"""Configuration contract tests: unsafe deployments must fail before external connections."""

import pytest

from socratic_partner.config import ConfigurationError, Settings

VALID_ENVIRONMENT = {
    "DISCORD_BOT_TOKEN": "test-token",
    "DISCORD_GUILD_ID": "100",
    "DISCORD_TEST_CHANNEL_ID": "200",
    "DISCORD_ALLOWED_USER_ID": "300",
    "SOCRATIC_PARTNER_TEST_MODE": "true",
    "SOCRATIC_PARTNER_LOG_LEVEL": "INFO",
}


def test_loads_valid_environment() -> None:
    """Document stable defaults through the public loader, without reading a real `.env`."""
    settings = Settings.from_environment(VALID_ENVIRONMENT, env_file=None)

    assert settings.discord_bot_token == "test-token"
    assert settings.discord_guild_id == 100
    assert settings.discord_test_channel_id == 200
    assert settings.discord_allowed_user_id == 300
    assert settings.test_mode is True
    assert settings.database_path.as_posix() == "data/socratic_partner.sqlite3"
    assert settings.default_interval_seconds == 24 * 60 * 60
    assert settings.pi_executable == "pi"
    assert settings.pi_session_directory.as_posix() == "data/pi-sessions"
    assert settings.pi_model is None
    assert settings.pi_timeout_seconds == 120


def test_rejects_missing_secret() -> None:
    environment = {**VALID_ENVIRONMENT, "DISCORD_BOT_TOKEN": ""}

    with pytest.raises(ConfigurationError, match="DISCORD_BOT_TOKEN is required"):
        Settings.from_environment(environment, env_file=None)


def test_rejects_non_numeric_identifier() -> None:
    environment = {**VALID_ENVIRONMENT, "DISCORD_GUILD_ID": "not-an-id"}

    with pytest.raises(ConfigurationError, match="DISCORD_GUILD_ID must be an integer"):
        Settings.from_environment(environment, env_file=None)


def test_rejects_invalid_default_interval() -> None:
    environment = {**VALID_ENVIRONMENT, "SOCRATIC_PARTNER_DEFAULT_INTERVAL_HOURS": "0"}

    with pytest.raises(
        ConfigurationError, match="SOCRATIC_PARTNER_DEFAULT_INTERVAL_HOURS must be positive"
    ):
        Settings.from_environment(environment, env_file=None)


def test_rejects_non_test_mode_during_first_increment() -> None:
    environment = {**VALID_ENVIRONMENT, "SOCRATIC_PARTNER_TEST_MODE": "false"}

    with pytest.raises(ConfigurationError, match="requires SOCRATIC_PARTNER_TEST_MODE=true"):
        Settings.from_environment(environment, env_file=None)
