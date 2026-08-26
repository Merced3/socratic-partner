"""Discord transport for the development status slice."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from . import __version__
from .config import Settings

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

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
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

    def _register_commands(self) -> None:
        @self.tree.command(name="status", description="Show Automation Lab connection status.")
        async def status(interaction: discord.Interaction) -> None:
            if not is_authorized(
                self.settings,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                user_id=interaction.user.id,
            ):
                logger.warning(
                    "Rejected /status from guild=%s channel=%s user=%s.",
                    interaction.guild_id,
                    interaction.channel_id,
                    interaction.user.id,
                )
                await interaction.response.send_message(
                    "This development command is not available here.", ephemeral=True
                )
                return

            latency_ms = round(self.latency * 1000)
            command_state = "ready" if self._commands_synced else "synchronizing"
            await interaction.response.send_message(
                "\n".join(
                    (
                        "**Sparring Partner — development status**",
                        f"- Version: `{__version__}`",
                        "- Mode: `test`",
                        f"- Discord: `connected` ({latency_ms} ms)",
                        f"- Commands: `{command_state}`",
                        "- Agent runtime: `not implemented`",
                        "- Persistence: `not implemented`",
                        "- Scheduling: `not implemented`",
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


def create_bot(settings: Settings) -> SparringPartnerBot:
    bot = SparringPartnerBot(settings)
    bot.tree.on_error = on_app_command_error
    return bot
