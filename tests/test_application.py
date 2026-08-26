"""Black-box application workflows use public operations, real SQLite, and recording ports."""

from __future__ import annotations

from collections import deque
from pathlib import Path

import pytest

from socratic_partner.application import (
    AgentRequestFailed,
    ConversationAlreadyOpen,
    MessageDeliveryFailed,
    SocraticApplication,
    WrongConversationChannel,
)
from socratic_partner.errors import ErrorKind
from socratic_partner.pi_rpc import PiRpcError, PiRunResult
from socratic_partner.store import ApplicationStatus, ConversationStatus, StateStore


class ScriptedAgent:
    """Protocol-shaped agent fake whose outputs are visible at the application boundary."""

    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = deque(responses)
        self.new_session_count = 0
        self.prompt_count = 0

    async def new_session(self) -> dict[str, object]:
        self.new_session_count += 1
        return {"sessionId": f"session-{self.new_session_count}"}

    async def prompt(self, message: str) -> PiRunResult:
        self.prompt_count += 1
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return PiRunResult(
            text=response,
            session_id=f"session-{self.new_session_count}",
            session_file=f"session-{self.new_session_count}.jsonl",
            provider="test-provider",
            model_id="test-model",
            input_tokens=10 * self.prompt_count,
            output_tokens=2 * self.prompt_count,
            cost=0.001 * self.prompt_count,
        )


class RecordingMessenger:
    """Message-port fake records observable sends/replies and can inject delivery failure."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str, int]] = []
        self.replies: list[tuple[object, str]] = []
        self.fail_next_send = False
        self.fail_next_reply = False

    async def send(self, channel_id: int, text: str) -> int:
        if self.fail_next_send:
            self.fail_next_send = False
            raise MessageDeliveryFailed("simulated delivery failure")
        message_id = 1_000 + len(self.sent)
        self.sent.append((channel_id, text, message_id))
        return message_id

    async def reply(self, reference: object, text: str) -> None:
        if self.fail_next_reply:
            self.fail_next_reply = False
            raise MessageDeliveryFailed("simulated reply failure")
        self.replies.append((reference, text))


def _store(path: Path) -> StateStore:
    store = StateStore(path, default_interval_seconds=86_400)
    store.initialize()
    return store


async def test_complete_conversation_workflow_survives_application_reconstruction(
    tmp_path,
) -> None:
    """Prove start→reply→restart→reply→done through public behavior and durable state."""
    database = tmp_path / "state.sqlite3"
    agent = ScriptedAgent(
        ["Opening question?", "First response?", "Second response?", "Session card"]
    )
    messenger = RecordingMessenger()
    first = SocraticApplication(
        store=_store(database), agent=agent, messenger=messenger
    )

    started = await first.start_conversation(channel_id=100)
    await first.reply(channel_id=100, reference="message-1", text="First answer")

    restarted_store = _store(database)
    restarted = SocraticApplication(
        store=restarted_store, agent=agent, messenger=messenger
    )
    await restarted.reply(
        channel_id=100, reference="message-2", text="Answer after restart"
    )
    completed = await restarted.complete_conversation(channel_id=100)

    durable = restarted_store.get_conversation(started.conversation.id)
    assert durable is not None
    assert durable.status is ConversationStatus.COMPLETED
    assert durable.session_card == "Session card"
    assert durable.completed_at is not None
    assert completed.state.next_question_at is not None
    assert (
        completed.state.next_question_at - durable.completed_at
    ).total_seconds() == pytest.approx(86_400)
    assert messenger.sent[0][1] == "Opening question?"
    assert messenger.sent[-1][1].endswith("Session card")
    assert messenger.replies == [
        ("message-1", "First response?"),
        ("message-2", "Second response?"),
    ]
    assert restarted_store.get_active_conversation() is None
    assert agent.new_session_count == 1


async def test_second_start_is_rejected_without_another_model_run(tmp_path) -> None:
    """One active conversation is a public routing invariant, independent of SQLite errors."""
    agent = ScriptedAgent(["Opening question?"])
    application = SocraticApplication(
        store=_store(tmp_path / "state.sqlite3"),
        agent=agent,
        messenger=RecordingMessenger(),
    )
    await application.start_conversation(channel_id=100)

    with pytest.raises(ConversationAlreadyOpen):
        await application.start_conversation(channel_id=100)

    assert agent.new_session_count == 1


async def test_wrong_channel_cannot_reply_or_complete(tmp_path) -> None:
    """A message from another channel must not alter or close the active conversation."""
    store = _store(tmp_path / "state.sqlite3")
    application = SocraticApplication(
        store=store,
        agent=ScriptedAgent(["Opening question?"]),
        messenger=RecordingMessenger(),
    )
    await application.start_conversation(channel_id=100)

    with pytest.raises(WrongConversationChannel):
        await application.reply(channel_id=200, reference="wrong", text="answer")
    with pytest.raises(WrongConversationChannel):
        await application.complete_conversation(channel_id=200)

    assert store.get_active_conversation() is not None


async def test_billing_failure_pauses_without_opening_conversation(tmp_path) -> None:
    """A failed opening cannot become active; billing policy must remain durable and visible."""
    store = _store(tmp_path / "state.sqlite3")
    application = SocraticApplication(
        store=store,
        agent=ScriptedAgent([PiRpcError("402 available credits exhausted")]),
        messenger=RecordingMessenger(),
    )

    with pytest.raises(AgentRequestFailed) as captured:
        await application.start_conversation(channel_id=100)

    assert captured.value.failure.kind is ErrorKind.BILLING
    assert store.get_active_conversation() is None
    assert store.get_state().status is ApplicationStatus.PAUSED


async def test_opening_delivery_failure_does_not_create_conversation(tmp_path) -> None:
    """A question is not open until its observable message has been delivered successfully."""
    store = _store(tmp_path / "state.sqlite3")
    messenger = RecordingMessenger()
    messenger.fail_next_send = True
    application = SocraticApplication(
        store=store,
        agent=ScriptedAgent(["Opening question?"]),
        messenger=messenger,
    )

    with pytest.raises(MessageDeliveryFailed):
        await application.start_conversation(channel_id=100)

    assert store.get_active_conversation() is None
    assert store.get_state().last_error_kind == "infrastructure"


async def test_failed_session_card_delivery_reopens_conversation(tmp_path) -> None:
    """`/done` may report failure, but the user must be able to retry the same conversation."""
    store = _store(tmp_path / "state.sqlite3")
    messenger = RecordingMessenger()
    application = SocraticApplication(
        store=store,
        agent=ScriptedAgent(["Opening question?", "Session card"]),
        messenger=messenger,
    )
    await application.start_conversation(channel_id=100)
    messenger.fail_next_send = True

    with pytest.raises(MessageDeliveryFailed):
        await application.complete_conversation(channel_id=100)

    active = store.get_active_conversation()
    assert active is not None
    assert active.status is ConversationStatus.OPEN
