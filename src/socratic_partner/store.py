"""SQLite-backed operational state for Socratic Partner."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

_SCHEMA_VERSION = 4
_SINGLETON_ID = 1


class ApplicationStatus(StrEnum):
    WAITING = "WAITING"
    PAUSED = "PAUSED"


class ConversationStatus(StrEnum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True, slots=True)
class Conversation:
    id: str
    status: ConversationStatus
    channel_id: int
    question_message_id: int
    session_card: str | None
    started_at: datetime
    completed_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ApplicationState:
    status: ApplicationStatus
    interval_seconds: int
    next_question_at: datetime | None
    last_error: str | None
    last_error_kind: str | None
    pi_session_id: str | None
    pi_session_file: str | None
    last_agent_call_at: datetime | None
    last_provider: str | None
    last_model_id: str | None
    last_input_tokens: int
    last_output_tokens: int
    last_cost: float
    created_at: datetime
    updated_at: datetime


class StateStore:
    """Persist the single running application's operational state."""

    def __init__(self, database_path: Path, *, default_interval_seconds: int) -> None:
        if default_interval_seconds <= 0:
            raise ValueError("default_interval_seconds must be positive")
        self.database_path = database_path
        self.default_interval_seconds = default_interval_seconds

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > _SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema {version} is newer than supported schema {_SCHEMA_VERSION}."
                )
            if version == 0:
                self._migrate_to_version_1(connection)
                version = 1
            if version == 1:
                self._migrate_to_version_2(connection)
                version = 2
            if version == 2:
                self._migrate_to_version_3(connection)
                version = 3
            if version == 3:
                self._migrate_to_version_4(connection)

    def get_state(self) -> ApplicationState:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT status, interval_seconds, next_question_at, last_error,
                       last_error_kind, pi_session_id, pi_session_file, last_agent_call_at,
                       last_provider, last_model_id, last_input_tokens,
                       last_output_tokens, last_cost, created_at, updated_at
                FROM application_state
                WHERE id = ?
                """,
                (_SINGLETON_ID,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Application state is missing; initialize the store first.")
        return _state_from_row(row)

    def get_active_conversation(self) -> Conversation | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, status, channel_id, question_message_id, session_card,
                       started_at, completed_at, updated_at
                FROM conversations
                WHERE status IN ('OPEN', 'CLOSING')
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
        return _conversation_from_row(row) if row is not None else None

    def start_conversation(
        self,
        *,
        conversation_id: str,
        channel_id: int,
        question_message_id: int,
        now: datetime | None = None,
    ) -> Conversation:
        timestamp = _as_utc(now or datetime.now(UTC)).isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO conversations (
                    id, status, channel_id, question_message_id, session_card,
                    started_at, completed_at, updated_at
                ) VALUES (?, 'OPEN', ?, ?, NULL, ?, NULL, ?)
                """,
                (conversation_id, channel_id, question_message_id, timestamp, timestamp),
            )
        conversation = self.get_active_conversation()
        if conversation is None:
            raise RuntimeError("Conversation was not created.")
        return conversation

    def mark_conversation_closing(
        self, conversation_id: str, *, now: datetime | None = None
    ) -> Conversation:
        timestamp = _as_utc(now or datetime.now(UTC)).isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE conversations
                SET status = 'CLOSING', updated_at = ?
                WHERE id = ? AND status = 'OPEN'
                """,
                (timestamp, conversation_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Open conversation was not available for closing.")
        conversation = self.get_active_conversation()
        if conversation is None:
            raise RuntimeError("Closing conversation is missing.")
        return conversation

    def reopen_conversation(
        self, conversation_id: str, *, now: datetime | None = None
    ) -> Conversation:
        timestamp = _as_utc(now or datetime.now(UTC)).isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE conversations
                SET status = 'OPEN', updated_at = ?
                WHERE id = ? AND status = 'CLOSING'
                """,
                (timestamp, conversation_id),
            )
        conversation = self.get_active_conversation()
        if conversation is None:
            raise RuntimeError("Conversation could not be reopened.")
        return conversation

    def complete_conversation(
        self,
        conversation_id: str,
        *,
        session_card: str,
        now: datetime | None = None,
    ) -> ApplicationState:
        timestamp = _as_utc(now or datetime.now(UTC))
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE conversations
                SET status = 'COMPLETED', session_card = ?, completed_at = ?, updated_at = ?
                WHERE id = ? AND status = 'CLOSING'
                """,
                (
                    session_card,
                    timestamp.isoformat(),
                    timestamp.isoformat(),
                    conversation_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Closing conversation was not available for completion.")
            state = connection.execute(
                "SELECT status, interval_seconds FROM application_state WHERE id = ?",
                (_SINGLETON_ID,),
            ).fetchone()
            if state is None:
                raise RuntimeError("Application state is missing.")
            next_question_at = None
            if state["status"] == ApplicationStatus.WAITING:
                next_question_at = (
                    timestamp + timedelta(seconds=state["interval_seconds"])
                ).isoformat()
            connection.execute(
                """
                UPDATE application_state
                SET next_question_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_question_at, timestamp.isoformat(), _SINGLETON_ID),
            )
        return self.get_state()

    def pause(self, *, now: datetime | None = None) -> ApplicationState:
        timestamp = _as_utc(now or datetime.now(UTC))
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE application_state
                SET status = ?, next_question_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (ApplicationStatus.PAUSED, timestamp.isoformat(), _SINGLETON_ID),
            )
        return self.get_state()

    def resume(self, *, now: datetime | None = None) -> ApplicationState:
        timestamp = _as_utc(now or datetime.now(UTC))
        with self._connection() as connection:
            row = connection.execute(
                "SELECT interval_seconds FROM application_state WHERE id = ?",
                (_SINGLETON_ID,),
            ).fetchone()
            if row is None:
                raise RuntimeError("Application state is missing; initialize the store first.")
            next_question_at = timestamp + timedelta(seconds=row["interval_seconds"])
            connection.execute(
                """
                UPDATE application_state
                SET status = ?, next_question_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    ApplicationStatus.WAITING,
                    next_question_at.isoformat(),
                    timestamp.isoformat(),
                    _SINGLETON_ID,
                ),
            )
        return self.get_state()

    def set_interval_hours(
        self, hours: int, *, now: datetime | None = None
    ) -> ApplicationState:
        if hours <= 0:
            raise ValueError("Interval hours must be positive.")
        timestamp = _as_utc(now or datetime.now(UTC))
        interval_seconds = hours * 60 * 60
        with self._connection() as connection:
            state = connection.execute(
                "SELECT status FROM application_state WHERE id = ?", (_SINGLETON_ID,)
            ).fetchone()
            if state is None:
                raise RuntimeError("Application state is missing.")
            active = connection.execute(
                "SELECT 1 FROM conversations WHERE status IN ('OPEN', 'CLOSING')"
            ).fetchone()
            next_question_at = None
            if state["status"] == ApplicationStatus.WAITING and active is None:
                next_question_at = (timestamp + timedelta(hours=hours)).isoformat()
            connection.execute(
                """
                UPDATE application_state
                SET interval_seconds = ?, next_question_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    interval_seconds,
                    next_question_at,
                    timestamp.isoformat(),
                    _SINGLETON_ID,
                ),
            )
        return self.get_state()

    def record_agent_success(
        self,
        *,
        session_id: str,
        session_file: str | None,
        provider: str | None,
        model_id: str | None,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        now: datetime | None = None,
    ) -> ApplicationState:
        timestamp = _as_utc(now or datetime.now(UTC))
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE application_state
                SET pi_session_id = ?, pi_session_file = ?, last_agent_call_at = ?,
                    last_provider = ?, last_model_id = ?, last_input_tokens = ?,
                    last_output_tokens = ?, last_cost = ?, last_error = NULL,
                    last_error_kind = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    session_id,
                    session_file,
                    timestamp.isoformat(),
                    provider,
                    model_id,
                    input_tokens,
                    output_tokens,
                    cost,
                    timestamp.isoformat(),
                    _SINGLETON_ID,
                ),
            )
        return self.get_state()

    def record_agent_error(
        self,
        error: str,
        *,
        kind: str = "unknown",
        pause_automation: bool = False,
        now: datetime | None = None,
    ) -> ApplicationState:
        timestamp = _as_utc(now or datetime.now(UTC))
        with self._connection() as connection:
            if pause_automation:
                connection.execute(
                    """
                    UPDATE application_state
                    SET last_error = ?, last_error_kind = ?, status = 'PAUSED',
                        next_question_at = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (error, kind, timestamp.isoformat(), _SINGLETON_ID),
                )
            else:
                connection.execute(
                    """
                    UPDATE application_state
                    SET last_error = ?, last_error_kind = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (error, kind, timestamp.isoformat(), _SINGLETON_ID),
                )
        return self.get_state()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _migrate_to_version_1(self, connection: sqlite3.Connection) -> None:
        timestamp = datetime.now(UTC).isoformat()
        connection.execute(
            """
            CREATE TABLE application_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                status TEXT NOT NULL CHECK (status IN ('WAITING', 'PAUSED')),
                interval_seconds INTEGER NOT NULL CHECK (interval_seconds > 0),
                next_question_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO application_state (
                id, status, interval_seconds, next_question_at,
                last_error, created_at, updated_at
            ) VALUES (?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                _SINGLETON_ID,
                ApplicationStatus.WAITING,
                self.default_interval_seconds,
                timestamp,
                timestamp,
            ),
        )
        connection.execute("PRAGMA user_version = 1")

    def _migrate_to_version_2(self, connection: sqlite3.Connection) -> None:
        columns = (
            "pi_session_id TEXT",
            "pi_session_file TEXT",
            "last_agent_call_at TEXT",
            "last_provider TEXT",
            "last_model_id TEXT",
            "last_input_tokens INTEGER NOT NULL DEFAULT 0",
            "last_output_tokens INTEGER NOT NULL DEFAULT 0",
            "last_cost REAL NOT NULL DEFAULT 0",
        )
        for definition in columns:
            connection.execute(f"ALTER TABLE application_state ADD COLUMN {definition}")
        connection.execute("PRAGMA user_version = 2")

    def _migrate_to_version_3(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSING', 'COMPLETED')),
                channel_id INTEGER NOT NULL,
                question_message_id INTEGER NOT NULL,
                session_card TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX one_active_conversation
            ON conversations ((1))
            WHERE status IN ('OPEN', 'CLOSING')
            """
        )
        connection.execute("PRAGMA user_version = 3")

    def _migrate_to_version_4(self, connection: sqlite3.Connection) -> None:
        connection.execute("ALTER TABLE application_state ADD COLUMN last_error_kind TEXT")
        connection.execute("PRAGMA user_version = 4")


def _conversation_from_row(row: sqlite3.Row) -> Conversation:
    return Conversation(
        id=row["id"],
        status=ConversationStatus(row["status"]),
        channel_id=row["channel_id"],
        question_message_id=row["question_message_id"],
        session_card=row["session_card"],
        started_at=_parse_required_datetime(row["started_at"]),
        completed_at=_parse_datetime(row["completed_at"]),
        updated_at=_parse_required_datetime(row["updated_at"]),
    )


def _state_from_row(row: sqlite3.Row) -> ApplicationState:
    return ApplicationState(
        status=ApplicationStatus(row["status"]),
        interval_seconds=row["interval_seconds"],
        next_question_at=_parse_datetime(row["next_question_at"]),
        last_error=row["last_error"],
        last_error_kind=row["last_error_kind"],
        pi_session_id=row["pi_session_id"],
        pi_session_file=row["pi_session_file"],
        last_agent_call_at=_parse_datetime(row["last_agent_call_at"]),
        last_provider=row["last_provider"],
        last_model_id=row["last_model_id"],
        last_input_tokens=row["last_input_tokens"],
        last_output_tokens=row["last_output_tokens"],
        last_cost=row["last_cost"],
        created_at=_parse_required_datetime(row["created_at"]),
        updated_at=_parse_required_datetime(row["updated_at"]),
    )


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _parse_required_datetime(value: str) -> datetime:
    parsed = _parse_datetime(value)
    if parsed is None:
        raise RuntimeError("Required timestamp is missing from application state.")
    return parsed


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamps must be timezone-aware.")
    return value.astimezone(UTC)
