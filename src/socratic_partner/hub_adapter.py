"""Socratic Partner's discord-hub adapter: commands, messages, scheduling.

The hub owns Discord; this module owns Socratic policy. Authorization
(channel/user gating) stays here by design — the hub delivers every
invocation and lets the project decide (ADR 0003).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

from . import __version__
from .application import (
    AgentRequestFailed,
    ConversationAlreadyOpen,
    ConversationNotOpen,
    MessageDeliveryFailed,
    NoActiveConversation,
    OperationBusy,
    SocraticApplication,
    StatePersistenceFailed,
    WrongConversationChannel,
)
from .config import Settings
from .errors import ClassifiedError, classify_error
from .hub_client import HubClient, HubError
from .operation_gate import OperationGate, OperationLease
from .pi_rpc import PiRpcClient, PiRpcError, PiRunResult
from .scheduler import AutomaticScheduler
from .store import ApplicationState, ConversationStatus, StateStore

logger = logging.getLogger(__name__)

_TYPING_REFRESH_SECONDS = 9.0
_REQUIRED_CHANNEL_PERMISSIONS = (
    "view_channel",
    "send_messages",
    "read_message_history",
    "create_public_threads",
    "send_messages_in_threads",
)


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """Opaque reply reference passed through the application layer."""

    message_id: str
    channel_id: int
    text: str


def message_authorized(
    settings: Settings,
    *,
    channel_id: int,
    user_id: int,
    parent_channel_id: int | None = None,
) -> bool:
    """Replies are valid in the home channel or in one of its session threads."""
    return (
        settings.test_mode
        and (
            channel_id == settings.discord_channel_id
            or parent_channel_id == settings.discord_channel_id
        )
        and user_id == settings.discord_allowed_user_id
    )


def command_authorized(
    settings: Settings,
    *,
    channel_id: int,
    user_id: int,
    active_conversation_channel_id: int | None,
) -> bool:
    """Commands are valid in the home channel or the active session thread.

    The hub's command payload does not identify a thread's parent, so a
    session thread is recognized as the active conversation's channel.
    """
    if not settings.test_mode or user_id != settings.discord_allowed_user_id:
        return False
    if channel_id == settings.discord_channel_id:
        return True
    return (
        active_conversation_channel_id is not None
        and channel_id == active_conversation_channel_id
    )


class HubConversationMessenger:
    """Translate the application's narrow message port into hub API calls."""

    def __init__(self, hub: HubClient) -> None:
        self.hub = hub

    async def send(self, channel_id: int, text: str) -> int:
        try:
            result = await self.hub.post_message(channel_id, text)
        except HubError as exc:
            raise MessageDeliveryFailed(str(exc)) from exc
        return int(result["id"])

    async def reply(self, reference: object, text: str) -> None:
        if not isinstance(reference, InboundMessage):
            raise MessageDeliveryFailed("Reply reference was not an inbound message.")
        try:
            await self.hub.post_message(
                reference.channel_id,
                text,
                reply_to_message_id=reference.message_id,
            )
        except HubError as exc:
            raise MessageDeliveryFailed(str(exc)) from exc


DeferredHandler = Callable[[dict], Awaitable[str]]
ImmediateHandler = Callable[[dict], Awaitable[dict]]


class SocraticHubAdapter:
    """Wire the application service, scheduler, and hub client together."""

    def __init__(
        self,
        settings: Settings,
        store: StateStore,
        pi_client: PiRpcClient,
        hub: HubClient,
    ) -> None:
        self.settings = settings
        self.store = store
        self.pi_client = pi_client
        self.hub = hub
        self.operation_gate = OperationGate()
        self.conversation_service = SocraticApplication(
            store=store,
            agent=pi_client,
            messenger=HubConversationMessenger(hub),
            operation_gate=self.operation_gate,
        )
        self.scheduler = (
            AutomaticScheduler(
                read_state=store.get_state,
                read_active_conversation=store.get_active_conversation,
                operation_gate=self.operation_gate,
                kickoff=self._automatic_kickoff,
                notify_failure=self._notify_automatic_failure,
            )
            if settings.automatic_scheduler_enabled
            else None
        )
        self._stopping = False
        self._stop_event = asyncio.Event()
        self._scheduler_clock = lambda: datetime.now(UTC)

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        """Verify the hub, claim the home channel, and publish commands."""
        health = await self.hub.health()
        if not health.get("discord_connected", False):
            raise HubError("discord-hub is up but not connected to Discord.")
        registered = {
            _safe_int(entry.get("channel_id"))
            for entry in await self.hub.get_registrations()
        }
        if self.settings.discord_channel_id not in registered:
            await self.hub.register_channel(
                self.settings.discord_channel_id,
                self.settings.callback_url,
                display_name="Socrates",
                avatar_url=self.settings.avatar_url,
            )
            logger.info("Registered the home channel with discord-hub.")
        result = await self.hub.put_commands(
            self.settings.callback_url, self._command_declarations()
        )
        logger.info("Synchronized %s command(s) through discord-hub.", result.get("synced"))

    async def close(self) -> None:
        self._stopping = True
        self._stop_event.set()
        await self.pi_client.close()
        await self.hub.close()

    async def run_scheduler(self) -> None:
        if self.scheduler is None:
            return
        logger.info("Automatic scheduler loop started.")
        while not self._stopping:
            try:
                await self.scheduler.tick(self._scheduler_clock())
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Automatic scheduler tick failed.")
            # Wake immediately on shutdown instead of sleeping through it.
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=60)

    # -- hub callback dispatch ----------------------------------------------

    async def dispatch(self, payload: dict) -> dict | None:
        """Handle one hub delivery; the return value is the interaction response."""
        if payload.get("type") == "command":
            return await self._handle_command(payload)
        asyncio.create_task(self._process_message(payload))
        return None

    async def _process_message(self, payload: dict) -> None:
        text = str(payload.get("text") or "").strip()
        if not text:
            return
        author = payload.get("author") or {}
        channel_id = _safe_int(payload.get("channel_id"))
        user_id = _safe_int(author.get("id"))
        thread = payload.get("thread") or {}
        parent_channel_id = _safe_int(thread.get("parent_channel_id"))
        if channel_id is None or user_id is None:
            return
        if not message_authorized(
            self.settings,
            channel_id=channel_id,
            user_id=user_id,
            parent_channel_id=parent_channel_id,
        ):
            return

        conversation = self.store.get_active_conversation()
        if (
            conversation is None
            or conversation.status is not ConversationStatus.OPEN
            or conversation.channel_id != channel_id
        ):
            return

        reference = InboundMessage(
            message_id=str(payload.get("message_id")),
            channel_id=channel_id,
            text=text,
        )
        try:
            await self._with_typing(
                channel_id,
                self.conversation_service.reply(
                    channel_id=channel_id, reference=reference, text=text
                ),
            )
        except (NoActiveConversation, WrongConversationChannel, ConversationNotOpen):
            return
        except OperationBusy as exc:
            await self._safe_post(channel_id, f"{exc} Retry shortly.")
        except AgentRequestFailed as exc:
            logger.exception("Socratic conversation turn failed.")
            await self._safe_post(
                channel_id,
                f"**Agent request failed**\n{exc.failure.discord_message()}",
            )
        except MessageDeliveryFailed:
            logger.exception("Could not deliver Socratic conversation response.")

    async def _handle_command(self, payload: dict) -> dict:
        command = str(payload.get("command") or "")
        channel_id = _safe_int(payload.get("channel_id")) or 0
        user = payload.get("user") or {}
        user_id = _safe_int(user.get("id")) or 0
        active = self.store.get_active_conversation()
        if not command_authorized(
            self.settings,
            channel_id=channel_id,
            user_id=user_id,
            active_conversation_channel_id=(
                active.channel_id if active is not None else None
            ),
        ):
            logger.warning(
                "Rejected command %r from channel=%s user=%s.", command, channel_id, user_id
            )
            return {
                "text": "This development command is not available here.",
                "ephemeral": True,
            }

        name = command.replace("-", "_")
        deferred = getattr(self, f"_deferred_{name}", None)
        if deferred is not None:
            interaction_id = str(payload.get("interaction_id"))
            asyncio.create_task(self._run_deferred(deferred, interaction_id, payload))
            return {"defer": True, "ephemeral": True}
        immediate = getattr(self, f"_immediate_{name}", None)
        if immediate is not None:
            return await immediate(payload)
        return {"text": "Unknown command.", "ephemeral": True}

    async def _run_deferred(
        self, handler: DeferredHandler, interaction_id: str, payload: dict
    ) -> None:
        try:
            text = await handler(payload)
        except Exception:
            logger.exception("Deferred command failed.")
            text = "The command failed. See the local application log for details."
        try:
            await self.hub.post_followup(interaction_id, text, ephemeral=True)
        except HubError:
            logger.exception("Could not deliver the deferred command response.")

    # -- immediate commands --------------------------------------------------

    async def _immediate_status(self, payload: dict) -> dict:
        state = self.store.get_state()
        conversation = self.store.get_active_conversation()
        try:
            health = await self.hub.health()
            hub_status = (
                "connected" if health.get("discord_connected") else "hub up, Discord down"
            )
        except HubError:
            hub_status = "unreachable"
        return {
            "text": "\n".join(
                (
                    "**Socratic Partner — development status**",
                    f"- Version: `{__version__}`",
                    "- Mode: `test`",
                    "- Test controls: "
                    f"`{'enabled' if self.settings.test_controls_enabled else 'disabled'}`",
                    f"- State: `{state.status}`",
                    f"- Conversation: `{_format_conversation(conversation)}`",
                    f"- Interval: `{_format_interval(state.interval_seconds)}`",
                    f"- Next activation: {_format_next_activation(state)}",
                    f"- Discord (via hub): `{hub_status}`",
                    "- Persistence: `ready`",
                    f"- Agent runtime: `{_format_agent_runtime(self.pi_client)}`",
                    f"- Pi session: `{_format_session(state)}`",
                    f"- Model: `{_format_model(state)}`",
                    f"- Last agent call: {_format_last_agent_call(state)}",
                    f"- Last recorded cost: `${state.last_cost:.6f}`",
                    f"- Last error category: `{state.last_error_kind or 'none'}`",
                    f"- Last error: `{_truncate_status(state.last_error or 'none')}`",
                    f"- Scheduler: `{_format_scheduler_status(self)}`",
                    f"- Current operation: `{self.operation_gate.current_operation or 'idle'}`",
                )
            ),
            "ephemeral": True,
        }

    async def _immediate_interval(self, payload: dict) -> dict:
        hours = int((payload.get("options") or {}).get("hours"))
        state = self.store.set_interval_hours(hours)
        active = self.store.get_active_conversation()
        timing = (
            "It will apply when the current conversation closes."
            if active is not None
            else f"Planned activation: {_format_next_activation(state)}."
        )
        return {
            "text": f"Interval set to **{_format_interval(state.interval_seconds)}**. {timing}",
            "ephemeral": True,
        }

    async def _immediate_test_interval(self, payload: dict) -> dict:
        minutes = int((payload.get("options") or {}).get("minutes"))
        state = self.store.set_interval_minutes(minutes)
        active = self.store.get_active_conversation()
        timing = (
            "It will apply when the current conversation closes."
            if active is not None
            else f"Planned activation: {_format_next_activation(state)}."
        )
        return {
            "text": (
                "Short **test interval** set to "
                f"**{_format_interval(state.interval_seconds)}**. {timing} "
                "Restore `/interval` to the intended hours after testing."
            ),
            "ephemeral": True,
        }

    async def _immediate_pause(self, payload: dict) -> dict:
        state = self.store.pause()
        return {
            "text": f"Socratic Partner is now **{state.status}**. The saved activation "
            "was cleared.",
            "ephemeral": True,
        }

    async def _immediate_resume(self, payload: dict) -> dict:
        state = self.store.resume()
        return {
            "text": " ".join(
                (
                    f"Socratic Partner is now **{state.status}**.",
                    f"Planned activation: {_format_next_activation(state)}.",
                    _format_scheduler_configuration(self.settings),
                )
            ),
            "ephemeral": True,
        }

    # -- deferred commands ---------------------------------------------------

    async def _deferred_ask_test(self, payload: dict) -> str:
        lease = self.operation_gate.try_acquire("running a Pi connectivity test")
        if lease is None:
            return _busy_message(self.operation_gate)
        try:
            async with lease:
                result = await self.pi_client.prompt(
                    "This is a Socratic Partner connectivity test. Reply with one "
                    "short sentence confirming that you can reason conversationally. "
                    "Do not use tools."
                )
            self._record_agent_result(result)
        except PiRpcError as exc:
            logger.exception("Pi connectivity test failed.")
            failure = self._record_agent_failure(exc)
            return failure.discord_message()

        response = result.text
        if len(response) > 1_800:
            response = f"{response[:1_797]}..."
        return "\n".join(
            (
                "**Pi connectivity test passed**",
                response,
                "",
                f"Session: `{result.session_id[:12]}`",
                f"Model: `{result.provider or 'unknown'}/{result.model_id or 'unknown'}`",
            )
        )

    async def _deferred_ask_now(self, payload: dict) -> str:
        missing = await self._missing_delivery_permissions()
        if missing:
            return (
                "The hub's bot cannot post in the home channel. Grant its role: "
                + ", ".join(missing)
                + "."
            )
        if self.store.get_active_conversation() is not None:
            return (
                "A Socratic conversation is already open. Use `/done` before "
                "starting another."
            )
        thread_id = await self._create_session_thread()
        try:
            await self.conversation_service.start_conversation(channel_id=thread_id)
        except OperationBusy as exc:
            return f"{exc} Retry shortly."
        except ConversationAlreadyOpen:
            return (
                "A Socratic conversation is already open. Use `/done` before "
                "starting another."
            )
        except AgentRequestFailed as exc:
            logger.exception("Could not start Socratic conversation.")
            return exc.failure.discord_message()
        except (MessageDeliveryFailed, StatePersistenceFailed):
            logger.exception("Could not persist or deliver Socratic conversation.")
            return (
                "The conversation could not be delivered or saved. Check `/status` "
                "and the local logs."
            )
        return (
            f"A new Socratic conversation is open in <#{thread_id}>. Reply normally "
            "in that thread and use `/done` when you want to close it."
        )

    async def _deferred_done(self, payload: dict) -> str:
        channel_id = _safe_int(payload.get("channel_id"))
        if channel_id is None:
            return "The conversation channel is unavailable."
        try:
            completed = await self.conversation_service.complete_conversation(
                channel_id=channel_id
            )
        except OperationBusy as exc:
            return f"{exc} Retry shortly."
        except NoActiveConversation:
            return "There is no active Socratic conversation."
        except WrongConversationChannel:
            return "The active conversation belongs to another channel."
        except AgentRequestFailed as exc:
            logger.exception("Could not complete Socratic conversation.")
            return (
                exc.failure.discord_message()
                + " The conversation remains open; retry `/done` when ready."
            )
        except (MessageDeliveryFailed, StatePersistenceFailed):
            logger.exception("Could not deliver or persist conversation closure.")
            return (
                "The conversation could not be closed safely and remains open. "
                "Retry `/done`."
            )
        return (
            "Conversation closed. The next interval begins from this completion "
            f"point: {_format_next_activation(completed.state)}."
        )

    async def _deferred_model(self, payload: dict) -> str:
        requested = str((payload.get("options") or {}).get("model") or "").strip()
        if not requested:
            try:
                models = await self.pi_client.get_available_models()
            except PiRpcError as exc:
                return f"Could not list models: {exc}"
            lines = ["**Available models** (use `/model` with `provider/model-id`):"]
            for available in models:
                provider = available.get("provider")
                model_id = available.get("id")
                if provider and model_id:
                    lines.append(f"- `{provider}/{model_id}` — {available.get('name') or model_id}")
            return "\n".join(lines) if len(lines) > 1 else "No models were reported by Pi."

        provider, separator, model_id = requested.partition("/")
        if not separator or not provider.strip() or not model_id.strip():
            return "Model must be `provider/model-id`. Use `/model` with no value to list."
        lease = self.operation_gate.try_acquire("switching the model")
        if lease is None:
            return _busy_message(self.operation_gate)
        try:
            async with lease:
                new_model = await self.pi_client.set_model(
                    provider.strip(), model_id.strip()
                )
        except PiRpcError as exc:
            logger.exception("Model switch failed.")
            return f"The model was not switched: {exc}"
        name = new_model.get("name") or new_model.get("id") or model_id
        return (
            f"Model switched to **{name}** (`{provider.strip()}/{model_id.strip()}`). "
            "It applies to the next model call, including any active conversation."
        )

    # -- scheduler glue --------------------------------------------------------

    async def _automatic_kickoff(self, lease: OperationLease) -> None:
        if self._stopping:
            return
        thread_id = await self._create_session_thread()
        await self.conversation_service.start_claimed_conversation(
            channel_id=thread_id,
            lease=lease,
        )

    async def _notify_automatic_failure(self, failure: ClassifiedError) -> None:
        await self.hub.post_message(
            self.settings.discord_channel_id,
            "**Automatic activation paused**\n" + failure.discord_message(),
        )

    # -- helpers ---------------------------------------------------------------

    async def _create_session_thread(self) -> int:
        try:
            result = await self.hub.create_thread(
                self.settings.discord_channel_id,
                _session_thread_name(datetime.now(UTC)),
            )
        except HubError as exc:
            raise MessageDeliveryFailed(str(exc)) from exc
        return int(result["id"])

    async def _missing_delivery_permissions(self) -> list[str]:
        try:
            granted = await self.hub.channel_permissions(
                self.settings.discord_channel_id
            )
        except HubError:
            logger.warning("Permission preflight unavailable; proceeding optimistically.")
            return []
        return [name for name in _REQUIRED_CHANNEL_PERMISSIONS if name not in granted]

    async def _with_typing(self, channel_id: int, awaitable: Awaitable) -> object:
        async def pulse() -> None:
            while True:
                with suppress(HubError):
                    await self.hub.typing(channel_id)
                await asyncio.sleep(_TYPING_REFRESH_SECONDS)

        task = asyncio.create_task(pulse())
        try:
            with suppress(HubError):
                await self.hub.typing(channel_id)
            return await awaitable
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _safe_post(self, channel_id: int, text: str) -> None:
        with suppress(HubError):
            await self.hub.post_message(channel_id, text)

    def _command_declarations(self) -> list[dict]:
        commands: list[dict] = [
            {"name": "status", "description": "Show Socratic Partner runtime status."},
            {"name": "ask-test", "description": "Run a safe Pi connectivity test."},
            {"name": "ask-now", "description": "Start a Socratic conversation now."},
            {"name": "done", "description": "Close the active Socratic conversation."},
            {
                "name": "interval",
                "description": "Set hours between conversations.",
                "options": [
                    {
                        "name": "hours",
                        "description": "Whole hours from 1 to 720 (30 days).",
                        "type": "integer",
                        "required": True,
                        "min_value": 1,
                        "max_value": 720,
                    }
                ],
            },
            {"name": "pause", "description": "Pause future Socratic Partner activation."},
            {"name": "resume", "description": "Resume from a fresh interval."},
            {
                "name": "model",
                "description": "Switch the model Socrates reasons with (empty lists models).",
                "options": [
                    {
                        "name": "model",
                        "description": "Model as provider/model-id.",
                        "type": "string",
                        "required": False,
                    }
                ],
            },
        ]
        if self.settings.test_mode and self.settings.test_controls_enabled:
            commands.append(
                {
                    "name": "test-interval",
                    "description": "Set a short interval for controlled scheduler testing.",
                    "options": [
                        {
                            "name": "minutes",
                            "description": "Whole minutes from 1 to 60 for testing only.",
                            "type": "integer",
                            "required": True,
                            "min_value": 1,
                            "max_value": 60,
                        }
                    ],
                }
            )
        return commands

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


def _safe_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _session_thread_name(now: datetime) -> str:
    """Name a session thread by its start time; LLM titles are a future option."""
    return f"Session {now.astimezone(UTC):%Y-%m-%d %H:%M} UTC"


def _format_scheduler_configuration(settings: Settings) -> str:
    state = "enabled" if settings.automatic_scheduler_enabled else "disabled"
    return f"Automatic scheduler configuration is **{state}** until restart."


def _format_scheduler_status(adapter: SocraticHubAdapter) -> str:
    if adapter.scheduler is None:
        return "disabled"
    if adapter.operation_gate.current_operation == "automatic kickoff":
        return "running"
    retry_at = adapter.scheduler.retry_at
    if retry_at is not None:
        return f"enabled-idle; retry at {retry_at.isoformat()}"
    return "enabled-idle"


def _busy_message(operation_gate: OperationGate) -> str:
    operation = operation_gate.current_operation or "another model operation"
    return f"Another model operation is active: {operation}. Retry shortly."


def _truncate_status(text: str, *, limit: int = 160) -> str:
    single_line = " ".join(text.split())
    return single_line if len(single_line) <= limit else f"{single_line[: limit - 3]}..."


def _format_interval(interval_seconds: int) -> str:
    hours, remainder = divmod(interval_seconds, 60 * 60)
    if remainder == 0:
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    minutes, remainder = divmod(interval_seconds, 60)
    if remainder == 0:
        return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    return f"{interval_seconds} seconds"


def _format_timestamp(value: datetime, *, style: str) -> str:
    """Discord-native timestamp markdown; no Discord library required."""
    return f"<t:{int(value.timestamp())}:{style}>"


def _format_next_activation(state: ApplicationState) -> str:
    if state.next_question_at is None:
        return "`not scheduled`"
    absolute = _format_timestamp(state.next_question_at, style="F")
    relative = _format_timestamp(state.next_question_at, style="R")
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
    absolute = _format_timestamp(state.last_agent_call_at, style="F")
    relative = _format_timestamp(state.last_agent_call_at, style="R")
    return f"{absolute} ({relative})"
