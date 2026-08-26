import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from socratic_partner.store import ApplicationStatus, StateStore


def test_initializes_waiting_state(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=86_400)

    store.initialize()
    state = store.get_state()

    assert state.status is ApplicationStatus.WAITING
    assert state.interval_seconds == 86_400
    assert state.next_question_at is None
    assert state.last_error is None


def test_pause_survives_new_store_instance(tmp_path) -> None:
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


def test_rejects_naive_operation_timestamp(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3", default_interval_seconds=86_400)
    store.initialize()

    with pytest.raises(ValueError, match="timezone-aware"):
        store.pause(now=datetime(2026, 8, 25, 12, 0))


def test_rejects_newer_database_schema(tmp_path) -> None:
    database_path = tmp_path / "state.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA user_version = 99")

    store = StateStore(database_path, default_interval_seconds=86_400)

    with pytest.raises(RuntimeError, match="newer than supported"):
        store.initialize()
