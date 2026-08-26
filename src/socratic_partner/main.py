"""Application entry point."""

from __future__ import annotations

import logging
from pathlib import Path

from .config import ConfigurationError, Settings
from .discord_bot import create_bot
from .pi_rpc import PiRpcClient
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
    state = store.get_state()
    pi_client = PiRpcClient(
        executable=settings.pi_executable,
        working_directory=Path.cwd().resolve(),
        session_directory=settings.pi_session_directory.resolve(),
        session_file=state.pi_session_file,
        model=settings.pi_model,
        timeout_seconds=settings.pi_timeout_seconds,
    )
    bot = create_bot(settings, store, pi_client)
    bot.run(settings.discord_bot_token, log_handler=None)


if __name__ == "__main__":
    main()
