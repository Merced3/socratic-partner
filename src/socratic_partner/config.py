"""Environment-based application configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class ConfigurationError(ValueError):
    """Raised when deployment configuration is missing or unsafe."""


@dataclass(frozen=True, slots=True)
class Settings:
    discord_bot_token: str
    discord_guild_id: int
    discord_test_channel_id: int
    discord_allowed_user_id: int
    test_mode: bool
    log_level: str
    database_path: Path
    default_interval_seconds: int
    pi_executable: str
    pi_session_directory: Path
    pi_model: str | None
    pi_timeout_seconds: int
    automatic_scheduler_enabled: bool

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        env_file: Path | str | None = ".env",
    ) -> Settings:
        if environment is None:
            if env_file is not None:
                load_dotenv(dotenv_path=env_file, override=False)
            environment = os.environ

        token = _required_text(environment, "DISCORD_BOT_TOKEN")
        guild_id = _required_positive_int(environment, "DISCORD_GUILD_ID")
        channel_id = _required_positive_int(environment, "DISCORD_TEST_CHANNEL_ID")
        user_id = _required_positive_int(environment, "DISCORD_ALLOWED_USER_ID")
        test_mode = _parse_bool(environment.get("SOCRATIC_PARTNER_TEST_MODE", "true"))
        log_level = environment.get("SOCRATIC_PARTNER_LOG_LEVEL", "INFO").strip().upper()
        database_path_value = environment.get(
            "SOCRATIC_PARTNER_DATABASE_PATH", "data/socratic_partner.sqlite3"
        ).strip()
        database_path = Path(database_path_value)
        default_interval_hours = _positive_int_with_default(
            environment, "SOCRATIC_PARTNER_DEFAULT_INTERVAL_HOURS", default=24
        )
        pi_executable = environment.get("SOCRATIC_PARTNER_PI_EXECUTABLE", "pi").strip()
        pi_session_directory_value = environment.get(
            "SOCRATIC_PARTNER_PI_SESSION_DIRECTORY", "data/pi-sessions"
        ).strip()
        pi_model = environment.get("SOCRATIC_PARTNER_PI_MODEL", "").strip() or None
        pi_timeout_seconds = _positive_int_with_default(
            environment, "SOCRATIC_PARTNER_PI_TIMEOUT_SECONDS", default=120
        )
        automatic_scheduler_enabled = _parse_bool(
            environment.get("SOCRATIC_PARTNER_AUTOMATIC_SCHEDULER_ENABLED", "false")
        )

        if not test_mode:
            raise ConfigurationError(
                "The first development increment requires SOCRATIC_PARTNER_TEST_MODE=true."
            )
        if log_level not in _VALID_LOG_LEVELS:
            raise ConfigurationError(
                f"SOCRATIC_PARTNER_LOG_LEVEL must be one of {sorted(_VALID_LOG_LEVELS)}."
            )
        if not database_path_value:
            raise ConfigurationError("SOCRATIC_PARTNER_DATABASE_PATH cannot be empty.")
        if not pi_executable:
            raise ConfigurationError("SOCRATIC_PARTNER_PI_EXECUTABLE cannot be empty.")
        if not pi_session_directory_value:
            raise ConfigurationError("SOCRATIC_PARTNER_PI_SESSION_DIRECTORY cannot be empty.")

        return cls(
            discord_bot_token=token,
            discord_guild_id=guild_id,
            discord_test_channel_id=channel_id,
            discord_allowed_user_id=user_id,
            test_mode=test_mode,
            log_level=log_level,
            database_path=database_path,
            default_interval_seconds=default_interval_hours * 60 * 60,
            pi_executable=pi_executable,
            pi_session_directory=Path(pi_session_directory_value),
            pi_model=pi_model,
            pi_timeout_seconds=pi_timeout_seconds,
            automatic_scheduler_enabled=automatic_scheduler_enabled,
        )


def _required_text(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} is required.")
    return value


def _required_positive_int(environment: Mapping[str, str], name: str) -> int:
    raw_value = _required_text(environment, name)
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be positive.")
    return value


def _positive_int_with_default(
    environment: Mapping[str, str], name: str, *, default: int
) -> int:
    raw_value = environment.get(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be positive.")
    return value


def _parse_bool(raw_value: str) -> bool:
    return raw_value.strip().lower() in _TRUE_VALUES
