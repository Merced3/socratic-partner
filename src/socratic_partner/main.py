"""Application entry point: the automation-harness owns the process lifecycle.

The harness provides the single-instance lock, graceful shutdown on
SIGINT/SIGTERM, supervised restart with backoff, structured logs, and
``data/status.json``. Socratic Partner supplies only its workflow.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from automation_harness import Harness, HarnessConfig, ServiceContext

from .config import ConfigurationError, Settings
from .discord_bot import create_bot
from .pi_rpc import PiRpcClient
from .prompts import SYSTEM_PROMPT
from .store import StateStore

logger = logging.getLogger(__name__)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def socratic_partner_service(ctx: ServiceContext, settings: Settings) -> None:
    """Run the Discord bot until the harness requests shutdown."""
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
        system_prompt=SYSTEM_PROMPT,
        timeout_seconds=settings.pi_timeout_seconds,
    )
    bot = create_bot(settings, store, pi_client)

    async def shutdown_when_asked() -> None:
        await ctx.stop_event.wait()
        logger.info("Shutdown requested by the automation harness.")
        await bot.close()

    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(bot.start(settings.discord_bot_token))
        tasks.create_task(shutdown_when_asked())


def main() -> None:
    try:
        settings = Settings.from_environment()
    except ConfigurationError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

    configure_logging(settings.log_level)
    harness = Harness(HarnessConfig(data_dir="data"), name="socratic-partner")

    async def service(ctx: ServiceContext) -> None:
        await socratic_partner_service(ctx, settings)

    harness.add_service("socratic-partner", service)
    harness.run()  # async runtime: the harness owns the event loop


if __name__ == "__main__":
    main()
