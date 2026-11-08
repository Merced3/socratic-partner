"""Opt-in managed-Postgres evidence; default CI stays SQLite-only and secret-free."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete

from socratic_partner.migration import copy_sqlite_to_postgres, verify_sqlite_against_postgres
from socratic_partner.store import ConversationStatus, StateStore, application_state, conversations

POSTGRES_URL_ENV = "SOCRATIC_PARTNER_TEST_POSTGRES_URL"


@pytest.mark.skipif(not os.environ.get(POSTGRES_URL_ENV), reason="opt-in Postgres URL not set")
def test_postgres_migration_and_public_lifecycle(tmp_path: Path) -> None:
    """The real dialect must preserve migrated values and normal public state transitions.

    This targets only an explicitly supplied throwaway database. It checks public
    behavior and deterministic checksums rather than overfitting to driver rows.
    """
    url = os.environ[POSTGRES_URL_ENV]
    engine = create_engine(url)
    StateStore(url, default_interval_seconds=86_400)._run_alembic_upgrade()
    with engine.begin() as connection:
        connection.execute(delete(conversations))
        connection.execute(delete(application_state))
    source = tmp_path / "source.sqlite3"
    sqlite_store = StateStore(source, default_interval_seconds=86_400)
    sqlite_store.initialize()
    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    sqlite_store.start_conversation(
        conversation_id="postgres-migration-test",
        channel_id=9_223_372_036_854_775_000,
        question_message_id=9_223_372_036_854_775_001,
        now=now,
    )
    sqlite_store.mark_conversation_closing("postgres-migration-test", now=now)
    sqlite_store.complete_conversation("postgres-migration-test", session_card="test", now=now)

    try:
        report = copy_sqlite_to_postgres(source, url)
        assert report["tables"]["application_state"]["match"] is True
        assert report["tables"]["conversations"]["source_rows"] == 1
        assert verify_sqlite_against_postgres(source, url)["tables"]["conversations"]["match"]

        store = StateStore(url, default_interval_seconds=3_600)
        store.initialize()  # Reinitialization is safe and must not overwrite copied state.
        conversation = store.get_conversation("postgres-migration-test")
        assert conversation is not None
        assert conversation.status is ConversationStatus.COMPLETED
        assert conversation.channel_id == 9_223_372_036_854_775_000
        assert conversation.started_at == now
        assert store.get_state().interval_seconds == 86_400
        assert store.pause(now=now).next_question_at is None
        assert store.resume(now=now).next_question_at == now + timedelta(seconds=86_400)
    finally:
        with engine.begin() as connection:
            connection.execute(delete(conversations))
            connection.execute(delete(application_state))
        engine.dispose()
