"""Verified one-way copy from the deployed SQLite schema 4 to empty Postgres tables."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select

from .store import StateStore, application_state, conversations

_TABLES = {"application_state": application_state, "conversations": conversations}
_TIMESTAMP_COLUMNS = {
    "next_question_at",
    "last_agent_call_at",
    "created_at",
    "updated_at",
    "started_at",
    "completed_at",
}


def copy_sqlite_to_postgres(sqlite_path: Path, postgres_url: str) -> dict[str, Any]:
    """Copy every row once, refusing to overwrite any existing destination records."""
    source = _read_sqlite(sqlite_path)
    store = StateStore(postgres_url, default_interval_seconds=86_400)
    store._run_alembic_upgrade()  # Schema-only: do not seed state before the empty check.
    if any(_read_postgres(store.engine, name) for name in _TABLES):
        raise RuntimeError("Postgres destination must be empty; refusing to overwrite records.")
    with store.engine.begin() as connection:
        for name, table in _TABLES.items():
            if source[name]:
                connection.execute(table.insert(), source[name])
    return verify_sqlite_against_postgres(sqlite_path, postgres_url)


def verify_sqlite_against_postgres(sqlite_path: Path, postgres_url: str) -> dict[str, Any]:
    """Compare canonical public values without emitting private row contents."""
    source = _read_sqlite(sqlite_path)
    engine = create_engine(postgres_url)
    report: dict[str, Any] = {"tables": {}}
    for name in _TABLES:
        source_rows = source[name]
        destination_rows = _read_postgres(engine, name)
        source_hash = _rows_checksum(source_rows)
        destination_hash = _rows_checksum(destination_rows)
        table_report = {
            "source_rows": len(source_rows),
            "destination_rows": len(destination_rows),
            "source_sha256": source_hash,
            "destination_sha256": destination_hash,
            "match": source_hash == destination_hash,
        }
        report["tables"][name] = table_report
        if not table_report["match"]:
            raise RuntimeError(f"Migration verification failed for {name}.")
    engine.dispose()
    return report


def _read_sqlite(path: Path) -> dict[str, list[dict[str, Any]]]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        if connection.execute("PRAGMA user_version").fetchone()[0] != 4:
            raise RuntimeError("Only deployed SQLite schema 4 can be copied.")
        return {
            name: [
                _canonical_row(dict(row))
                for row in connection.execute(f"SELECT * FROM {name} ORDER BY id")
            ]
            for name in _TABLES
        }
    finally:
        connection.close()


def _read_postgres(engine, name: str) -> list[dict[str, Any]]:
    table = _TABLES[name]
    with engine.connect() as connection:
        return [
            _canonical_row(dict(row._mapping))
            for row in connection.execute(select(table).order_by(table.c.id))
        ]


def _canonical_row(row: dict[str, Any]) -> dict[str, Any]:
    canonical = {}
    for key, value in row.items():
        if key in _TIMESTAMP_COLUMNS and value is not None:
            if isinstance(value, str):
                value = datetime.fromisoformat(value)
            if value.tzinfo is not None:
                value = value.astimezone(UTC).replace(tzinfo=None)
            canonical[key] = value.isoformat(timespec="microseconds")
        else:
            canonical[key] = value
    return canonical


def _rows_checksum(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
