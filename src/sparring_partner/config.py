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
        test_mode = _parse_bool(environment.get("SPARRING_PARTNER_TEST_MODE", "true"))
        log_level = environment.get("SPARRING_PARTNER_LOG_LEVEL", "INFO").strip().upper()

        if not test_mode:
            raise ConfigurationError(
                "The first development increment requires SPARRING_PARTNER_TEST_MODE=true."
            )
        if log_level not in _VALID_LOG_LEVELS:
            raise ConfigurationError(
                f"SPARRING_PARTNER_LOG_LEVEL must be one of {sorted(_VALID_LOG_LEVELS)}."
            )

        return cls(
            discord_bot_token=token,
            discord_guild_id=guild_id,
            discord_test_channel_id=channel_id,
            discord_allowed_user_id=user_id,
            test_mode=test_mode,
            log_level=log_level,
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


def _parse_bool(raw_value: str) -> bool:
    return raw_value.strip().lower() in _TRUE_VALUES
