"""Application entry point: the automation-harness owns the process lifecycle.

The harness provides the single-instance lock, graceful stop on
SIGINT/SIGTERM, supervised restart with backoff, structured logs, and
``data/status.json``. Discord interaction goes through the local
discord-hub; Socratic Partner runs a small callback server for inbound
deliveries and contains no Discord library at all.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import uvicorn
from automation_harness import Harness, HarnessConfig, ServiceContext

from .callback_server import create_callback_app
from .config import ConfigurationError, Settings
from .hub_adapter import SocraticHubAdapter
from .hub_client import HubClient
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
    """Run the hub adapter and callback server until the harness stops them."""
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
    hub = HubClient(settings.hub_url)
    adapter = SocraticHubAdapter(settings, store, pi_client, hub)
    await adapter.start()  # fails (and the harness retries) if the hub is down

    callback_app = create_callback_app(adapter.dispatch)
    server = uvicorn.Server(
        uvicorn.Config(
            callback_app,
            host=settings.callback_host,
            port=settings.callback_port,
            log_level=settings.log_level.lower(),
        )
    )

    async def stop_when_asked() -> None:
        await ctx.stop_event.wait()
        logger.info("Stop requested by the automation harness.")
        server.should_exit = True

    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(server.serve())
            tasks.create_task(adapter.run_scheduler())
            tasks.create_task(stop_when_asked())
    finally:
        await adapter.close()


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
