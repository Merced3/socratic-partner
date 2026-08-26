"""Application-level Socratic conversation operations, independent of Discord."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from .errors import ClassifiedError, classify_error
from .operation_gate import OperationGate, OperationLease
from .pi_rpc import PiRpcError, PiRunResult
from .prompts import OPENING_PROMPT, SESSION_CARD_PROMPT
from .store import ApplicationState, Conversation, ConversationStatus, StateStore


class AgentRuntime(Protocol):
    async def new_session(self) -> dict[str, object]: ...

    async def prompt(self, message: str) -> PiRunResult: ...


class ConversationMessenger(Protocol):
    async def send(self, channel_id: int, text: str) -> int: ...

    async def reply(self, reference: object, text: str) -> None: ...


class ApplicationError(RuntimeError):
    """Base error for a public conversation operation."""


class ConversationAlreadyOpen(ApplicationError):
    pass


class OperationBusy(ApplicationError):
    def __init__(self, operation: str) -> None:
        super().__init__(f"Another model operation is active: {operation}.")
        self.operation = operation


class InvalidOperationLease(ApplicationError):
    pass


class NoActiveConversation(ApplicationError):
    pass


class WrongConversationChannel(ApplicationError):
    pass


class ConversationNotOpen(ApplicationError):
    pass


class AgentRequestFailed(ApplicationError):
    def __init__(self, failure: ClassifiedError) -> None:
        super().__init__(failure.detail)
        self.failure = failure


class MessageDeliveryFailed(ApplicationError):
    pass


class StatePersistenceFailed(ApplicationError):
    pass


@dataclass(frozen=True, slots=True)
class StartedConversation:
    conversation: Conversation
    question: str


@dataclass(frozen=True, slots=True)
class CompletedConversation:
    state: ApplicationState
    session_card: str


class SocraticApplication:
    """Coordinate agent, durable state, and observable conversation messages."""

    def __init__(
        self,
        *,
        store: StateStore,
        agent: AgentRuntime,
        messenger: ConversationMessenger,
        operation_gate: OperationGate,
    ) -> None:
        self.store = store
        self.agent = agent
        self.messenger = messenger
        self.operation_gate = operation_gate

    async def start_conversation(self, *, channel_id: int) -> StartedConversation:
        lease = self.operation_gate.try_acquire("starting a Socratic conversation")
        if lease is None:
            raise OperationBusy(self.operation_gate.current_operation or "unknown")
        async with lease:
            return await self._start_conversation(channel_id=channel_id)

    async def start_claimed_conversation(
        self, *, channel_id: int, lease: OperationLease
    ) -> StartedConversation:
        """Start under a gate lease already acquired by an activation adapter."""
        if not self.operation_gate.is_current(lease):
            raise InvalidOperationLease(
                "The supplied operation lease is not active on this application."
            )
        return await self._start_conversation(channel_id=channel_id)

    async def _start_conversation(self, *, channel_id: int) -> StartedConversation:
        if self.store.get_active_conversation() is not None:
            raise ConversationAlreadyOpen("A Socratic conversation is already open.")

        try:
            await self.agent.new_session()
            result = await self.agent.prompt(OPENING_PROMPT)
        except PiRpcError as exc:
            raise self._record_agent_failure(exc) from exc

        self._record_agent_result(result)
        try:
            message_id = await self.messenger.send(channel_id, result.text)
            conversation = self.store.start_conversation(
                conversation_id=uuid4().hex,
                channel_id=channel_id,
                question_message_id=message_id,
            )
        except MessageDeliveryFailed as exc:
            self.store.record_agent_error(str(exc), kind="infrastructure")
            raise
        except (sqlite3.Error, RuntimeError) as exc:
            self.store.record_agent_error(str(exc), kind="infrastructure")
            raise StatePersistenceFailed(str(exc)) from exc

        return StartedConversation(conversation=conversation, question=result.text)

    async def reply(
        self,
        *,
        channel_id: int,
        reference: object,
        text: str,
    ) -> str:
        lease = self.operation_gate.try_acquire("replying to a Socratic conversation")
        if lease is None:
            raise OperationBusy(self.operation_gate.current_operation or "unknown")
        async with lease:
            return await self._reply(
                channel_id=channel_id, reference=reference, text=text
            )

    async def _reply(
        self,
        *,
        channel_id: int,
        reference: object,
        text: str,
    ) -> str:
        conversation = self._require_active_conversation(channel_id)
        if conversation.status is not ConversationStatus.OPEN:
            raise ConversationNotOpen("The Socratic conversation is not open for replies.")

        try:
            result = await self.agent.prompt(text.strip())
        except PiRpcError as exc:
            raise self._record_agent_failure(exc) from exc

        self._record_agent_result(result)
        try:
            await self.messenger.reply(reference, result.text)
        except MessageDeliveryFailed as exc:
            self.store.record_agent_error(str(exc), kind="infrastructure")
            raise
        return result.text

    async def complete_conversation(self, *, channel_id: int) -> CompletedConversation:
        lease = self.operation_gate.try_acquire("completing a Socratic conversation")
        if lease is None:
            raise OperationBusy(self.operation_gate.current_operation or "unknown")
        async with lease:
            return await self._complete_conversation(channel_id=channel_id)

    async def _complete_conversation(
        self, *, channel_id: int
    ) -> CompletedConversation:
        conversation = self._require_active_conversation(channel_id)
        if conversation.status is ConversationStatus.CLOSING:
            conversation = self.store.reopen_conversation(conversation.id)

        try:
            self.store.mark_conversation_closing(conversation.id)
            result = await self.agent.prompt(SESSION_CARD_PROMPT)
            self._record_agent_result(result)
            await self.messenger.send(
                channel_id, f"**Provisional session card**\n{result.text}"
            )
            state = self.store.complete_conversation(
                conversation.id, session_card=result.text
            )
        except PiRpcError as exc:
            self._reopen_after_failed_completion(conversation.id)
            raise self._record_agent_failure(exc) from exc
        except MessageDeliveryFailed as exc:
            self.store.record_agent_error(str(exc), kind="infrastructure")
            self._reopen_after_failed_completion(conversation.id)
            raise
        except (sqlite3.Error, RuntimeError) as exc:
            self.store.record_agent_error(str(exc), kind="infrastructure")
            self._reopen_after_failed_completion(conversation.id)
            raise StatePersistenceFailed(str(exc)) from exc

        return CompletedConversation(state=state, session_card=result.text)

    def _require_active_conversation(self, channel_id: int) -> Conversation:
        conversation = self.store.get_active_conversation()
        if conversation is None:
            raise NoActiveConversation("There is no active Socratic conversation.")
        if conversation.channel_id != channel_id:
            raise WrongConversationChannel(
                "The active conversation belongs to another channel."
            )
        return conversation

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

    def _record_agent_failure(self, error: PiRpcError) -> AgentRequestFailed:
        failure = classify_error(str(error))
        self.store.record_agent_error(
            failure.detail,
            kind=failure.kind,
            pause_automation=failure.should_pause_automation,
        )
        return AgentRequestFailed(failure)

    def _reopen_after_failed_completion(self, conversation_id: str) -> None:
        conversation = self.store.get_active_conversation()
        if conversation is not None and conversation.status is ConversationStatus.CLOSING:
            self.store.reopen_conversation(conversation_id)
