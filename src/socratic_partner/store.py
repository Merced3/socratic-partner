"""SQLite-backed operational state for Socratic Partner."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

_SCHEMA_VERSION = 1
_SINGLETON_ID = 1


class ApplicationStatus(StrEnum):
    WAITING = "WAITING"
    PAUSED = "PAUSED"


@dataclass(frozen=True, slots=True)
class ApplicationState:
    status: ApplicationStatus
    interval_seconds: int
    next_question_at: datetime | None
    last_error: str | None
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

    def get_state(self) -> ApplicationState:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT status, interval_seconds, next_question_at, last_error,
                       created_at, updated_at
                FROM application_state
                WHERE id = ?
                """,
                (_SINGLETON_ID,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Application state is missing; initialize the store first.")
        return _state_from_row(row)

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
        connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")


def _state_from_row(row: sqlite3.Row) -> ApplicationState:
    return ApplicationState(
        status=ApplicationStatus(row["status"]),
        interval_seconds=row["interval_seconds"],
        next_question_at=_parse_datetime(row["next_question_at"]),
        last_error=row["last_error"],
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
