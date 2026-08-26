"""Real-SQLite integration tests assert durable public state rather than SQL implementation."""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from socratic_partner.store import ApplicationStatus, ConversationStatus, StateStore


def test_initializes_waiting_state(tmp_path) -> None:
    """A fresh deployment needs a safe idle state before any model or Discord activity."""
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=86_400)

    store.initialize()
    state = store.get_state()

    assert state.status is ApplicationStatus.WAITING
    assert state.interval_seconds == 86_400
    assert state.next_question_at is None
    assert state.last_error is None


def test_pause_survives_new_store_instance(tmp_path) -> None:
    """User pause is a durable safety control; reconstruction simulates process restart."""
    database_path = tmp_path / "state.sqlite3"
    store = StateStore(database_path, default_interval_seconds=86_400)
    store.initialize()

    paused_at = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    store.pause(now=paused_at)

    restarted_store = StateStore(database_path, default_interval_seconds=3_600)
    restarted_store.initialize()
    state = restarted_store.get_state()

    assert state.status is ApplicationStatus.PAUSED
    assert state.interval_seconds == 86_400
    assert state.next_question_at is None
    assert state.updated_at == paused_at


def test_resume_starts_fresh_interval_and_survives_restart(tmp_path) -> None:
    """Resume starts one fresh interval and preserves that public state across reconstruction."""
    database_path = tmp_path / "state.sqlite3"
    store = StateStore(database_path, default_interval_seconds=7_200)
    store.initialize()
    store.pause(now=datetime(2026, 8, 25, 10, 0, tzinfo=UTC))

    resumed_at = datetime(2026, 8, 25, 11, 30, tzinfo=UTC)
    state = store.resume(now=resumed_at)

    restarted_store = StateStore(database_path, default_interval_seconds=86_400)
    restarted_store.initialize()
    restarted_state = restarted_store.get_state()

    assert state.status is ApplicationStatus.WAITING
    assert state.next_question_at == resumed_at + timedelta(hours=2)
    assert restarted_state == state


def test_records_agent_runtime_and_clears_previous_error(tmp_path) -> None:
    """A successful model run must replace stale failure status with inspectable runtime facts."""
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=86_400)
    store.initialize()
    failed_at = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    store.record_agent_error("temporary failure", now=failed_at)

    completed_at = datetime(2026, 8, 25, 12, 5, tzinfo=UTC)
    state = store.record_agent_success(
        session_id="session-123",
        session_file="C:/sessions/session.jsonl",
        provider="test-provider",
        model_id="test-model",
        input_tokens=120,
        output_tokens=15,
        cost=0.0042,
        now=completed_at,
    )

    assert state.pi_session_id == "session-123"
    assert state.pi_session_file == "C:/sessions/session.jsonl"
    assert state.last_agent_call_at == completed_at
    assert state.last_provider == "test-provider"
    assert state.last_model_id == "test-model"
    assert state.last_input_tokens == 120
    assert state.last_output_tokens == 15
    assert state.last_cost == pytest.approx(0.0042)
    assert state.last_error is None


def test_conversation_lifecycle_sets_next_interval(tmp_path) -> None:
    """The outer interval begins at successful `/done`, not at conversation kickoff."""
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=7_200)
    store.initialize()
    started_at = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)

    conversation = store.start_conversation(
        conversation_id="conversation-1",
        channel_id=100,
        question_message_id=200,
        now=started_at,
    )
    assert conversation.status is ConversationStatus.OPEN

    closing = store.mark_conversation_closing("conversation-1", now=started_at)
    assert closing.status is ConversationStatus.CLOSING

    completed_at = started_at + timedelta(minutes=15)
    state = store.complete_conversation(
        "conversation-1", session_card="Provisional card", now=completed_at
    )

    assert store.get_active_conversation() is None
    assert state.next_question_at == completed_at + timedelta(hours=2)


def test_paused_completion_does_not_schedule_next_question(tmp_path) -> None:
    """Completing a conversation must not override the user's durable pause decision."""
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=7_200)
    store.initialize()
    now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    store.start_conversation(
        conversation_id="conversation-1",
        channel_id=100,
        question_message_id=200,
        now=now,
    )
    store.pause(now=now)
    store.mark_conversation_closing("conversation-1", now=now)

    state = store.complete_conversation(
        "conversation-1", session_card="Provisional card", now=now
    )

    assert state.status is ApplicationStatus.PAUSED
    assert state.next_question_at is None


def test_only_one_conversation_can_be_active(tmp_path) -> None:
    """One-user conversation routing is ambiguous if two conversations can be active."""
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=86_400)
    store.initialize()
    store.start_conversation(
        conversation_id="conversation-1", channel_id=100, question_message_id=200
    )

    with pytest.raises(sqlite3.IntegrityError):
        store.start_conversation(
            conversation_id="conversation-2", channel_id=100, question_message_id=201
        )


def test_interval_updates_due_time_when_idle(tmp_path) -> None:
    """Changing an idle interval must expose a newly calculated due time through public state."""
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=86_400)
    store.initialize()
    changed_at = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)

    state = store.set_interval_hours(6, now=changed_at)

    assert state.interval_seconds == 6 * 60 * 60
    assert state.next_question_at == changed_at + timedelta(hours=6)


def test_interval_waits_for_active_conversation_completion(tmp_path) -> None:
    """An active session owns timing until `/done`; interval changes must not schedule over it."""
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=86_400)
    store.initialize()
    changed_at = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    store.start_conversation(
        conversation_id="conversation-1",
        channel_id=100,
        question_message_id=200,
        now=changed_at,
    )

    state = store.set_interval_hours(6, now=changed_at)

    assert state.interval_seconds == 6 * 60 * 60
    assert state.next_question_at is None


def test_billing_error_pauses_automation(tmp_path) -> None:
    """Billing failure requires operator action, so persisted future activation must stop."""
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=86_400)
    store.initialize()

    state = store.record_agent_error(
        "402 credits exhausted", kind="billing", pause_automation=True
    )

    assert state.status is ApplicationStatus.PAUSED
    assert state.next_question_at is None
    assert state.last_error_kind == "billing"


def test_rejects_naive_operation_timestamp(tmp_path) -> None:
    """Reject timezone-ambiguous writes before they corrupt cross-restart scheduling semantics."""
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=86_400)
    store.initialize()

    with pytest.raises(ValueError, match="timezone-aware"):
        store.pause(now=datetime(2026, 8, 25, 12, 0))


def test_rejects_newer_database_schema(tmp_path) -> None:
    """Older code must fail visibly instead of silently damaging data written by newer code."""
    database_path = tmp_path / "state.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA user_version = 99")

    store = StateStore(database_path, default_interval_seconds=86_400)

    with pytest.raises(RuntimeError, match="newer than supported"):
        store.initialize()
