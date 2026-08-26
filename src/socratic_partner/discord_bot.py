"""Discord transport for the development status slice."""

from __future__ import annotations

import logging
from contextlib import suppress

import discord
from discord import app_commands
from discord.ext import commands

from . import __version__
from .application import (
    AgentRequestFailed,
    ConversationAlreadyOpen,
    ConversationNotOpen,
    MessageDeliveryFailed,
    NoActiveConversation,
    SocraticApplication,
    StatePersistenceFailed,
    WrongConversationChannel,
)
from .config import Settings
from .errors import ClassifiedError, classify_error
from .pi_rpc import PiRpcClient, PiRpcError, PiRunResult
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


class SocraticPartnerBot(commands.Bot):
    """Discord bot restricted to one development guild, channel, and user."""

    def __init__(
        self, settings: Settings, store: StateStore, pi_client: PiRpcClient
    ) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.store = store
        self.pi_client = pi_client
        self._messenger = _DiscordConversationMessenger(self)
        self.conversation_service = SocraticApplication(
            store=store,
            agent=pi_client,
            messenger=self._messenger,
        )
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
        conversation = self.store.get_active_conversation()
        if conversation is not None:
            logger.info(
                "Recovered %s conversation %s.", conversation.status, conversation.id
            )

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.content.strip():
            return
        if not is_authorized(
            self.settings,
            guild_id=message.guild.id if message.guild else None,
            channel_id=message.channel.id,
            user_id=message.author.id,
        ):
            return

        try:
            async with message.channel.typing():
                await self.conversation_service.reply(
                    channel_id=message.channel.id,
                    reference=message,
                    text=message.content,
                )
        except (NoActiveConversation, WrongConversationChannel, ConversationNotOpen):
            return
        except AgentRequestFailed as exc:
            logger.exception("Socratic conversation turn failed.")
            with suppress(discord.HTTPException):
                await message.reply(
                    f"**Agent request failed**\n{exc.failure.discord_message()}",
                    mention_author=False,
                )
        except MessageDeliveryFailed:
            logger.exception("Could not deliver Socratic conversation response.")

    async def close(self) -> None:
        await self.pi_client.close()
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
        @self.tree.command(name="status", description="Show Socratic Partner runtime status.")
        async def status(interaction: discord.Interaction) -> None:
            if not await self._require_authorized(interaction):
                return

            state = self.store.get_state()
            conversation = self.store.get_active_conversation()
            missing_permissions = _missing_delivery_permissions(interaction)
            delivery_status = (
                "ready"
                if not missing_permissions
                else f"blocked ({', '.join(missing_permissions)})"
            )
            latency_ms = round(self.latency * 1000)
            command_state = "ready" if self._commands_synced else "synchronizing"
            await interaction.response.send_message(
                "\n".join(
                    (
                        "**Socratic Partner — development status**",
                        f"- Version: `{__version__}`",
                        "- Mode: `test`",
                        f"- State: `{state.status}`",
                        f"- Conversation: `{_format_conversation(conversation)}`",
                        f"- Interval: `{_format_interval(state.interval_seconds)}`",
                        f"- Next activation: {_format_next_activation(state)}",
                        f"- Discord: `connected` ({latency_ms} ms)",
                        f"- Channel delivery: `{delivery_status}`",
                        f"- Commands: `{command_state}`",
                        "- Persistence: `ready`",
                        f"- Agent runtime: `{_format_agent_runtime(self.pi_client)}`",
                        f"- Pi session: `{_format_session(state)}`",
                        f"- Model: `{_format_model(state)}`",
                        f"- Last agent call: {_format_last_agent_call(state)}",
                        f"- Last recorded cost: `${state.last_cost:.6f}`",
                        f"- Last error category: `{state.last_error_kind or 'none'}`",
                        f"- Last error: `{_truncate_status(state.last_error or 'none')}`",
                        "- Scheduler: `not running`",
                    )
                ),
                ephemeral=True,
            )

        @self.tree.command(name="ask-test", description="Run a safe Pi connectivity test.")
        async def ask_test(interaction: discord.Interaction) -> None:
            if not await self._require_authorized(interaction):
                return

            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                result = await self.pi_client.prompt(
                    "This is a Socratic Partner connectivity test. Reply with one short "
                    "sentence confirming that you can reason conversationally. Do not use tools."
                )
                self.store.record_agent_success(
                    session_id=result.session_id,
                    session_file=result.session_file,
                    provider=result.provider,
                    model_id=result.model_id,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost=result.cost,
                )
            except PiRpcError as exc:
                logger.exception("Pi connectivity test failed.")
                failure = self._record_agent_failure(exc)
                await interaction.followup.send(
                    failure.discord_message(), ephemeral=True
                )
                return

            response = result.text
            if len(response) > 1_800:
                response = f"{response[:1_797]}..."
            await interaction.followup.send(
                "\n".join(
                    (
                        "**Pi connectivity test passed**",
                        response,
                        "",
                        f"Session: `{result.session_id[:12]}`",
                        f"Model: `{result.provider or 'unknown'}/{result.model_id or 'unknown'}`",
                    )
                ),
                ephemeral=True,
            )

        @self.tree.command(name="ask-now", description="Start a Socratic conversation now.")
        async def ask_now(interaction: discord.Interaction) -> None:
            if not await self._require_authorized(interaction):
                return
            if interaction.channel is None:
                await interaction.response.send_message(
                    "The configured conversation channel is unavailable.", ephemeral=True
                )
                return
            missing_permissions = _missing_delivery_permissions(interaction)
            if missing_permissions:
                await interaction.response.send_message(
                    "Automation Lab cannot post normal messages in this channel. Grant its "
                    "bot role: " + ", ".join(missing_permissions) + ".",
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                await self.conversation_service.start_conversation(
                    channel_id=interaction.channel.id
                )
            except ConversationAlreadyOpen:
                await interaction.followup.send(
                    "A Socratic conversation is already open. Use `/done` before starting another.",
                    ephemeral=True,
                )
                return
            except AgentRequestFailed as exc:
                logger.exception("Could not start Socratic conversation.")
                await interaction.followup.send(
                    exc.failure.discord_message(), ephemeral=True
                )
                return
            except (MessageDeliveryFailed, StatePersistenceFailed):
                logger.exception("Could not persist or deliver Socratic conversation.")
                await interaction.followup.send(
                    "The conversation could not be delivered or saved. Check `/status` and the "
                    "local logs.",
                    ephemeral=True,
                )
                return

            await interaction.followup.send(
                "A new Socratic conversation is open. Reply normally in this channel and use "
                "`/done` when you want to close it.",
                ephemeral=True,
            )

        @self.tree.command(name="done", description="Close the active Socratic conversation.")
        async def done(interaction: discord.Interaction) -> None:
            if not await self._require_authorized(interaction):
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            if interaction.channel_id is None:
                await interaction.followup.send(
                    "The conversation channel is unavailable.", ephemeral=True
                )
                return
            try:
                completed = await self.conversation_service.complete_conversation(
                    channel_id=interaction.channel_id
                )
            except NoActiveConversation:
                await interaction.followup.send(
                    "There is no active Socratic conversation.", ephemeral=True
                )
                return
            except WrongConversationChannel:
                await interaction.followup.send(
                    "The active conversation belongs to another channel.", ephemeral=True
                )
                return
            except AgentRequestFailed as exc:
                logger.exception("Could not complete Socratic conversation.")
                await interaction.followup.send(
                    exc.failure.discord_message()
                    + " The conversation remains open; retry `/done` when ready.",
                    ephemeral=True,
                )
                return
            except (MessageDeliveryFailed, StatePersistenceFailed):
                logger.exception("Could not deliver or persist conversation closure.")
                await interaction.followup.send(
                    "The conversation could not be closed safely and remains open. Retry `/done`.",
                    ephemeral=True,
                )
                return

            state = completed.state

            await interaction.followup.send(
                "Conversation closed. The next interval begins from this completion point: "
                f"{_format_next_activation(state)}.",
                ephemeral=True,
            )

        @self.tree.command(name="interval", description="Set hours between conversations.")
        @app_commands.describe(hours="Whole hours from 1 to 720 (30 days).")
        async def interval(
            interaction: discord.Interaction,
            hours: app_commands.Range[int, 1, 720],
        ) -> None:
            if not await self._require_authorized(interaction):
                return

            state = self.store.set_interval_hours(hours)
            active = self.store.get_active_conversation()
            timing = (
                "It will apply when the current conversation closes."
                if active is not None
                else f"Planned activation: {_format_next_activation(state)}."
            )
            await interaction.response.send_message(
                f"Interval set to **{_format_interval(state.interval_seconds)}**. {timing}",
                ephemeral=True,
            )

        @self.tree.command(name="pause", description="Pause future Socratic Partner activation.")
        async def pause(interaction: discord.Interaction) -> None:
            if not await self._require_authorized(interaction):
                return

            state = self.store.pause()
            await interaction.response.send_message(
                f"Socratic Partner is now **{state.status}**. The saved activation was cleared.",
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
                        f"Socratic Partner is now **{state.status}**.",
                        f"Planned activation: {_format_next_activation(state)}.",
                        "The scheduler is not implemented yet.",
                    )
                ),
                ephemeral=True,
            )

    def _record_agent_result(self, result: PiRunResult) -> None:
        self.store.record_agent_success(
            session_id=result.session_id,
            session_file=result.session_file,
            provider=result.provider,
            model_id=result.model_id,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost=result.cost,
        )

    def _record_agent_failure(self, error: PiRpcError) -> ClassifiedError:
        failure = classify_error(str(error))
        self.store.record_agent_error(
            failure.detail,
            kind=failure.kind,
            pause_automation=failure.should_pause_automation,
        )
        return failure


class _DiscordConversationMessenger:
    """Translate the application's narrow message port into Discord operations."""

    def __init__(self, bot: SocraticPartnerBot) -> None:
        self.bot = bot

    async def send(self, channel_id: int, text: str) -> int:
        try:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(channel_id)
            message = await channel.send(_truncate_discord_message(text))
        except (discord.HTTPException, AttributeError) as exc:
            raise MessageDeliveryFailed(str(exc)) from exc
        return message.id

    async def reply(self, reference: object, text: str) -> None:
        if not isinstance(reference, discord.Message):
            raise MessageDeliveryFailed("Discord reply reference was not a message.")
        try:
            await _reply_in_chunks(reference, text)
        except discord.HTTPException as exc:
            raise MessageDeliveryFailed(str(exc)) from exc


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


def _missing_delivery_permissions(interaction: discord.Interaction) -> list[str]:
    guild = interaction.guild
    channel = interaction.channel
    if guild is None or guild.me is None or channel is None:
        return ["View Channel", "Send Messages", "Read Message History"]
    permissions_for = getattr(channel, "permissions_for", None)
    if permissions_for is None:
        return ["View Channel", "Send Messages", "Read Message History"]

    permissions = permissions_for(guild.me)
    required = (
        ("view_channel", "View Channel"),
        ("send_messages", "Send Messages"),
        ("read_message_history", "Read Message History"),
    )
    return [label for attribute, label in required if not getattr(permissions, attribute)]


async def _reply_in_chunks(message: discord.Message, text: str) -> None:
    chunks = _discord_chunks(text)
    await message.reply(chunks[0], mention_author=False)
    for chunk in chunks[1:]:
        await message.channel.send(chunk)


def _discord_chunks(text: str, *, limit: int = 1_900) -> list[str]:
    content = text.strip() or "(No text response.)"
    return [content[index : index + limit] for index in range(0, len(content), limit)]


def _truncate_discord_message(text: str, *, limit: int = 1_900) -> str:
    content = text.strip() or "(No text response.)"
    if len(content) <= limit:
        return content
    return f"{content[: limit - 3]}..."


def _truncate_status(text: str, *, limit: int = 160) -> str:
    single_line = " ".join(text.split())
    return single_line if len(single_line) <= limit else f"{single_line[: limit - 3]}..."


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


def _format_conversation(conversation: object | None) -> str:
    if conversation is None:
        return "none"
    status = getattr(conversation, "status", "unknown")
    identifier = str(getattr(conversation, "id", ""))[:8]
    return f"{status} ({identifier})"


def _format_agent_runtime(pi_client: PiRpcClient) -> str:
    return "running" if pi_client.is_running else "ready (starts on demand)"


def _format_session(state: ApplicationState) -> str:
    return state.pi_session_id[:12] if state.pi_session_id else "not created"


def _format_model(state: ApplicationState) -> str:
    if state.last_provider and state.last_model_id:
        return f"{state.last_provider}/{state.last_model_id}"
    return "not recorded"


def _format_last_agent_call(state: ApplicationState) -> str:
    if state.last_agent_call_at is None:
        return "`never`"
    absolute = discord.utils.format_dt(state.last_agent_call_at, style="F")
    relative = discord.utils.format_dt(state.last_agent_call_at, style="R")
    return f"{absolute} ({relative})"


def create_bot(
    settings: Settings, store: StateStore, pi_client: PiRpcClient
) -> SocraticPartnerBot:
    bot = SocraticPartnerBot(settings, store, pi_client)
    bot.tree.on_error = on_app_command_error
    return bot
