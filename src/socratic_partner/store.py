"""Durable application state in SQLite (development/tests) or managed Postgres."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Connection,
    DateTime,
    Double,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
    text,
)

_SCHEMA_VERSION = 4
_SINGLETON_ID = 1

metadata = MetaData()
# BigInteger also preserves Discord snowflakes on the SQLite development dialect.
snowflake = BigInteger().with_variant(Integer, "sqlite")


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


# One metadata definition is shared by Alembic, migration verification, and the public store.
application_state = Table(
    "application_state",
    metadata,
    # Postgres owns the final schema; SQLite keeps its historical schema for upgrade tests.
    Column("id", Integer, primary_key=True),
    Column(
        "status", String, CheckConstraint("status IN ('WAITING', 'PAUSED')"), nullable=False
    ),
    Column(
        "interval_seconds", Integer, CheckConstraint("interval_seconds > 0"), nullable=False
    ),
    Column("next_question_at", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("pi_session_id", Text),
    Column("pi_session_file", Text),
    Column("last_agent_call_at", DateTime(timezone=True)),
    Column("last_provider", Text),
    Column("last_model_id", Text),
    Column("last_input_tokens", Integer, nullable=False, default=0),
    Column("last_output_tokens", Integer, nullable=False, default=0),
    Column("last_cost", Double, nullable=False, default=0),
    Column("last_error_kind", Text),
    CheckConstraint("id = 1"),
)
conversations = Table(
    "conversations",
    metadata,
    Column("id", Text, primary_key=True),
    Column(
        "status",
        String,
        CheckConstraint("status IN ('OPEN', 'CLOSING', 'COMPLETED')"),
        nullable=False,
    ),
    Column("channel_id", snowflake, nullable=False),
    Column("question_message_id", snowflake, nullable=False),
    Column("session_card", Text),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index(
        "one_active_conversation",
        "status",
        unique=True,
        postgresql_where=text("status IN ('OPEN', 'CLOSING')"),
    ),
)


class StateStore:
    """Persist one application's state through the same public API on either dialect."""

    def __init__(self, database: Path | str, *, default_interval_seconds: int) -> None:
        if default_interval_seconds <= 0:
            raise ValueError("default_interval_seconds must be positive")
        self.default_interval_seconds = default_interval_seconds
        self.database_url = (
            f"sqlite:///{database.as_posix()}" if isinstance(database, Path) else database
        )
        self.engine = create_engine(
            self.database_url,
            connect_args={"timeout": 5} if self.database_url.startswith("sqlite") else {},
        )
        database_name = self.engine.url.database
        self.database_path = (
            Path(database_name)
            if self.engine.dialect.name == "sqlite" and database_name not in (None, ":memory:")
            else None
        )

    def initialize(self) -> None:
        if self.engine.dialect.name == "sqlite":
            if self.database_path is None:
                raise RuntimeError("SQLite migration requires a filesystem path.")
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize_legacy_sqlite()
            return
        if self.engine.dialect.name != "postgresql":
            raise RuntimeError(f"Unsupported database dialect: {self.engine.dialect.name}")
        self._run_alembic_upgrade()
        timestamp = datetime.now(UTC)
        with self._connection() as connection:
            if connection.execute(
                select(application_state.c.id).where(application_state.c.id == _SINGLETON_ID)
            ).first() is None:
                connection.execute(
                    application_state.insert().values(
                        id=_SINGLETON_ID,
                        status=ApplicationStatus.WAITING.value,
                        interval_seconds=self.default_interval_seconds,
                        next_question_at=None,
                        last_error=None,
                        created_at=timestamp,
                        updated_at=timestamp,
                        last_input_tokens=0,
                        last_output_tokens=0,
                        last_cost=0,
                    )
                )

    def get_state(self) -> ApplicationState:
        with self._connection() as connection:
            row = connection.execute(
                select(application_state).where(application_state.c.id == _SINGLETON_ID)
            ).first()
        if row is None:
            raise RuntimeError("Application state is missing; initialize the store first.")
        return _state_from_row(row)

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        with self._connection() as connection:
            row = connection.execute(
                select(conversations).where(conversations.c.id == conversation_id)
            ).first()
        return _conversation_from_row(row) if row is not None else None

    def get_active_conversation(self) -> Conversation | None:
        with self._connection() as connection:
            row = connection.execute(
                select(conversations)
                .where(
                    conversations.c.status.in_(
                        (ConversationStatus.OPEN, ConversationStatus.CLOSING)
                    )
                )
                .order_by(conversations.c.started_at.desc())
                .limit(1)
            ).first()
        return _conversation_from_row(row) if row is not None else None

    def get_latest_conversation_in_channel(self, channel_id: int) -> Conversation | None:
        with self._connection() as connection:
            row = connection.execute(
                select(conversations)
                .where(conversations.c.channel_id == channel_id)
                .order_by(conversations.c.started_at.desc())
                .limit(1)
            ).first()
        return _conversation_from_row(row) if row is not None else None

    def delete_conversation(
        self, conversation_id: str, *, now: datetime | None = None
    ) -> ApplicationState:
        """Delete test data; discarding an active conversation restarts its interval."""
        timestamp = _as_utc(now or datetime.now(UTC))
        with self._connection() as connection:
            row = connection.execute(
                select(conversations.c.status).where(conversations.c.id == conversation_id)
            ).first()
            if row is None:
                raise RuntimeError("Conversation is missing.")
            connection.execute(conversations.delete().where(conversations.c.id == conversation_id))
            if row.status in (ConversationStatus.OPEN, ConversationStatus.CLOSING):
                state = connection.execute(
                    select(application_state.c.status, application_state.c.interval_seconds).where(
                        application_state.c.id == _SINGLETON_ID
                    )
                ).first()
                if state is None:
                    raise RuntimeError("Application state is missing.")
                next_question_at = None
                if state.status == ApplicationStatus.WAITING:
                    next_question_at = timestamp + timedelta(seconds=state.interval_seconds)
                connection.execute(
                    application_state.update()
                    .where(application_state.c.id == _SINGLETON_ID)
                    .values(next_question_at=next_question_at, updated_at=timestamp)
                )
        return self.get_state()

    def start_conversation(
        self,
        *,
        conversation_id: str,
        channel_id: int,
        question_message_id: int,
        now: datetime | None = None,
    ) -> Conversation:
        timestamp = _as_utc(now or datetime.now(UTC))
        with self._connection() as connection:
            connection.execute(
                conversations.insert().values(
                    id=conversation_id,
                    status=ConversationStatus.OPEN.value,
                    channel_id=channel_id,
                    question_message_id=question_message_id,
                    session_card=None,
                    started_at=timestamp,
                    completed_at=None,
                    updated_at=timestamp,
                )
            )
        conversation = self.get_active_conversation()
        if conversation is None:
            raise RuntimeError("Conversation was not created.")
        return conversation

    def mark_conversation_closing(
        self, conversation_id: str, *, now: datetime | None = None
    ) -> Conversation:
        timestamp = _as_utc(now or datetime.now(UTC))
        with self._connection() as connection:
            result = connection.execute(
                conversations.update()
                .where(conversations.c.id == conversation_id)
                .where(conversations.c.status == ConversationStatus.OPEN.value)
                .values(status=ConversationStatus.CLOSING.value, updated_at=timestamp)
            )
            if result.rowcount != 1:
                raise RuntimeError("Open conversation was not available for closing.")
        conversation = self.get_active_conversation()
        if conversation is None:
            raise RuntimeError("Closing conversation is missing.")
        return conversation

    def reopen_conversation(
        self, conversation_id: str, *, now: datetime | None = None
    ) -> Conversation:
        timestamp = _as_utc(now or datetime.now(UTC))
        with self._connection() as connection:
            connection.execute(
                conversations.update()
                .where(conversations.c.id == conversation_id)
                .where(conversations.c.status == ConversationStatus.CLOSING.value)
                .values(status=ConversationStatus.OPEN.value, updated_at=timestamp)
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
            result = connection.execute(
                conversations.update()
                .where(conversations.c.id == conversation_id)
                .where(conversations.c.status == ConversationStatus.CLOSING.value)
                .values(
                    status=ConversationStatus.COMPLETED.value,
                    session_card=session_card,
                    completed_at=timestamp,
                    updated_at=timestamp,
                )
            )
            if result.rowcount != 1:
                raise RuntimeError("Closing conversation was not available for completion.")
            state = connection.execute(
                select(application_state.c.status, application_state.c.interval_seconds).where(
                    application_state.c.id == _SINGLETON_ID
                )
            ).first()
            if state is None:
                raise RuntimeError("Application state is missing.")
            next_question_at = None
            if state.status == ApplicationStatus.WAITING:
                next_question_at = timestamp + timedelta(seconds=state.interval_seconds)
            connection.execute(
                application_state.update()
                .where(application_state.c.id == _SINGLETON_ID)
                .values(next_question_at=next_question_at, updated_at=timestamp)
            )
        return self.get_state()

    def pause(self, *, now: datetime | None = None) -> ApplicationState:
        timestamp = _as_utc(now or datetime.now(UTC))
        with self._connection() as connection:
            connection.execute(
                application_state.update()
                .where(application_state.c.id == _SINGLETON_ID)
                .values(
                    status=ApplicationStatus.PAUSED.value,
                    next_question_at=None,
                    updated_at=timestamp,
                )
            )
        return self.get_state()

    def resume(self, *, now: datetime | None = None) -> ApplicationState:
        timestamp = _as_utc(now or datetime.now(UTC))
        with self._connection() as connection:
            row = connection.execute(
                select(application_state.c.interval_seconds).where(
                    application_state.c.id == _SINGLETON_ID
                )
            ).first()
            if row is None:
                raise RuntimeError("Application state is missing; initialize the store first.")
            next_question_at = timestamp + timedelta(seconds=row.interval_seconds)
            connection.execute(
                application_state.update()
                .where(application_state.c.id == _SINGLETON_ID)
                .values(
                    status=ApplicationStatus.WAITING.value,
                    next_question_at=next_question_at,
                    updated_at=timestamp,
                )
            )
        return self.get_state()

    def set_interval_hours(self, hours: int, *, now: datetime | None = None) -> ApplicationState:
        if hours <= 0:
            raise ValueError("Interval hours must be positive.")
        return self._set_interval_seconds(hours * 60 * 60, now=now)

    def set_interval_minutes(
        self, minutes: int, *, now: datetime | None = None
    ) -> ApplicationState:
        if minutes <= 0:
            raise ValueError("Interval minutes must be positive.")
        return self._set_interval_seconds(minutes * 60, now=now)

    def _set_interval_seconds(
        self, interval_seconds: int, *, now: datetime | None = None
    ) -> ApplicationState:
        timestamp = _as_utc(now or datetime.now(UTC))
        with self._connection() as connection:
            state = connection.execute(
                select(application_state.c.status).where(application_state.c.id == _SINGLETON_ID)
            ).first()
            if state is None:
                raise RuntimeError("Application state is missing.")
            active = connection.execute(
                select(conversations.c.id)
                .where(
                    conversations.c.status.in_(
                        (ConversationStatus.OPEN, ConversationStatus.CLOSING)
                    )
                )
                .limit(1)
            ).first()
            next_question_at = None
            if state.status == ApplicationStatus.WAITING and active is None:
                next_question_at = timestamp + timedelta(seconds=interval_seconds)
            connection.execute(
                application_state.update()
                .where(application_state.c.id == _SINGLETON_ID)
                .values(
                    interval_seconds=interval_seconds,
                    next_question_at=next_question_at,
                    updated_at=timestamp,
                )
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
                application_state.update()
                .where(application_state.c.id == _SINGLETON_ID)
                .values(
                    pi_session_id=session_id,
                    pi_session_file=session_file,
                    last_agent_call_at=timestamp,
                    last_provider=provider,
                    last_model_id=model_id,
                    last_input_tokens=input_tokens,
                    last_output_tokens=output_tokens,
                    last_cost=cost,
                    last_error=None,
                    last_error_kind=None,
                    updated_at=timestamp,
                )
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
        values = {"last_error": error, "last_error_kind": kind, "updated_at": timestamp}
        if pause_automation:
            values.update(status=ApplicationStatus.PAUSED.value, next_question_at=None)
        with self._connection() as connection:
            connection.execute(
                application_state.update()
                .where(application_state.c.id == _SINGLETON_ID)
                .values(**values)
            )
        return self.get_state()

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        with self.engine.begin() as connection:
            yield connection

    def _run_alembic_upgrade(self) -> None:
        config = Config()
        migrations = Path(__file__).with_name("migrations")
        config.set_main_option("script_location", str(migrations))
        config.set_main_option("sqlalchemy.url", self.database_url)
        script = ScriptDirectory.from_config(config)
        with self.engine.connect() as connection:
            current = set(MigrationContext.configure(connection).get_current_heads())
        known = set(script.get_heads())
        if not current.issubset(known):
            raise RuntimeError(
                f"Database schema {sorted(current)} is newer than supported schema {sorted(known)}."
            )
        command.upgrade(config, "head")

    def _initialize_legacy_sqlite(self) -> None:
        """Retain deployed SQLite upgrades; new production Postgres uses Alembic."""
        with sqlite3.connect(self.database_path, timeout=5) as connection:
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
        for definition in (
            "pi_session_id TEXT",
            "pi_session_file TEXT",
            "last_agent_call_at TEXT",
            "last_provider TEXT",
            "last_model_id TEXT",
            "last_input_tokens INTEGER NOT NULL DEFAULT 0",
            "last_output_tokens INTEGER NOT NULL DEFAULT 0",
            "last_cost REAL NOT NULL DEFAULT 0",
        ):
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


def _conversation_from_row(row) -> Conversation:
    values = row._mapping
    return Conversation(
        id=values["id"],
        status=ConversationStatus(values["status"]),
        channel_id=values["channel_id"],
        question_message_id=values["question_message_id"],
        session_card=values["session_card"],
        started_at=_parse_required_datetime(values["started_at"]),
        completed_at=_parse_datetime(values["completed_at"]),
        updated_at=_parse_required_datetime(values["updated_at"]),
    )


def _state_from_row(row) -> ApplicationState:
    values = row._mapping
    return ApplicationState(
        status=ApplicationStatus(values["status"]),
        interval_seconds=values["interval_seconds"],
        next_question_at=_parse_datetime(values["next_question_at"]),
        last_error=values["last_error"],
        last_error_kind=values["last_error_kind"],
        pi_session_id=values["pi_session_id"],
        pi_session_file=values["pi_session_file"],
        last_agent_call_at=_parse_datetime(values["last_agent_call_at"]),
        last_provider=values["last_provider"],
        last_model_id=values["last_model_id"],
        last_input_tokens=values["last_input_tokens"],
        last_output_tokens=values["last_output_tokens"],
        last_cost=values["last_cost"],
        created_at=_parse_required_datetime(values["created_at"]),
        updated_at=_parse_required_datetime(values["updated_at"]),
    )


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    # SQLite's DATETIME processor drops the offset; persisted values are UTC by contract.
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _parse_required_datetime(value: datetime | str) -> datetime:
    parsed = _parse_datetime(value)
    if parsed is None:
        raise RuntimeError("Required timestamp is missing from application state.")
    return parsed


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamps must be timezone-aware.")
    return value.astimezone(UTC)
