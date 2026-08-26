"""Discord transport for the development status slice."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from . import __version__
from .config import Settings
from .store import ApplicationState, StateStore

logger = logging.getLogger(__name__)


def is_authorized(
    settings: Settings,
    *,
    guild_id: int | None,
    channel_id: int | None,
    user_id: int,
) -> bool:
    """Return whether an interaction is inside the explicit development boundary."""
    return (
        settings.test_mode
        and guild_id == settings.discord_guild_id
        and channel_id == settings.discord_test_channel_id
        and user_id == settings.discord_allowed_user_id
    )


class SparringPartnerBot(commands.Bot):
    """Discord bot restricted to one development guild, channel, and user."""

    def __init__(self, settings: Settings, store: StateStore) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.store = store
        self._commands_synced = False
        self._register_commands()

    async def setup_hook(self) -> None:
        guild = discord.Object(id=self.settings.discord_guild_id)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        self._commands_synced = True
        logger.info("Synchronized %d command(s) to the development guild.", len(synced))

    async def on_ready(self) -> None:
        if self.user is None:
            return
        logger.info("Connected to Discord as %s (%s).", self.user, self.user.id)

    async def close(self) -> None:
        logger.info("Closing Discord connection.")
        await super().close()

    async def _require_authorized(self, interaction: discord.Interaction) -> bool:
        if is_authorized(
            self.settings,
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            user_id=interaction.user.id,
        ):
            return True

        logger.warning(
            "Rejected command from guild=%s channel=%s user=%s.",
            interaction.guild_id,
            interaction.channel_id,
            interaction.user.id,
        )
        await interaction.response.send_message(
            "This development command is not available here.", ephemeral=True
        )
        return False

    def _register_commands(self) -> None:
        @self.tree.command(name="status", description="Show Sparring Partner runtime status.")
        async def status(interaction: discord.Interaction) -> None:
            if not await self._require_authorized(interaction):
                return

            state = self.store.get_state()
            latency_ms = round(self.latency * 1000)
            command_state = "ready" if self._commands_synced else "synchronizing"
            await interaction.response.send_message(
                "\n".join(
                    (
                        "**Sparring Partner — development status**",
                        f"- Version: `{__version__}`",
                        "- Mode: `test`",
                        f"- State: `{state.status}`",
                        f"- Interval: `{_format_interval(state.interval_seconds)}`",
                        f"- Next activation: {_format_next_activation(state)}",
                        f"- Discord: `connected` ({latency_ms} ms)",
                        f"- Commands: `{command_state}`",
                        "- Persistence: `ready`",
                        "- Agent runtime: `not implemented`",
                        "- Scheduler: `not running`",
                    )
                ),
                ephemeral=True,
            )

        @self.tree.command(name="pause", description="Pause future Sparring Partner activation.")
        async def pause(interaction: discord.Interaction) -> None:
            if not await self._require_authorized(interaction):
                return

            state = self.store.pause()
            await interaction.response.send_message(
                f"Sparring Partner is now **{state.status}**. The saved activation was cleared.",
                ephemeral=True,
            )

        @self.tree.command(name="resume", description="Resume from a fresh interval.")
        async def resume(interaction: discord.Interaction) -> None:
            if not await self._require_authorized(interaction):
                return

            state = self.store.resume()
            await interaction.response.send_message(
                " ".join(
                    (
                        f"Sparring Partner is now **{state.status}**.",
                        f"Planned activation: {_format_next_activation(state)}.",
                        "The scheduler is not implemented yet.",
                    )
                ),
                ephemeral=True,
            )


async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Return a private generic error while retaining diagnostic details in logs."""
    logger.exception("Discord application command failed.", exc_info=error)
    message = "The command failed. See the local application log for details."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


def _format_interval(interval_seconds: int) -> str:
    hours, remainder = divmod(interval_seconds, 60 * 60)
    if remainder == 0:
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    return f"{interval_seconds} seconds"


def _format_next_activation(state: ApplicationState) -> str:
    if state.next_question_at is None:
        return "`not scheduled`"
    absolute = discord.utils.format_dt(state.next_question_at, style="F")
    relative = discord.utils.format_dt(state.next_question_at, style="R")
    return f"{absolute} ({relative})"


def create_bot(settings: Settings, store: StateStore) -> SparringPartnerBot:
    bot = SparringPartnerBot(settings, store)
    bot.tree.on_error = on_app_command_error
    return bot
