"""Application entry point."""

from __future__ import annotations

import logging

from .config import ConfigurationError, Settings
from .discord_bot import create_bot
from .store import StateStore


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    try:
        settings = Settings.from_environment()
    except ConfigurationError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

    configure_logging(settings.log_level)
    store = StateStore(
        settings.database_path,
        default_interval_seconds=settings.default_interval_seconds,
    )
    store.initialize()
    bot = create_bot(settings, store)
    bot.run(settings.discord_bot_token, log_handler=None)


if __name__ == "__main__":
    main()
