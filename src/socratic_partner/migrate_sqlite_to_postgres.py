"""CLI for the reviewed, one-way SQLite schema-4 to managed-Postgres copy."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .migration import copy_sqlite_to_postgres, verify_sqlite_against_postgres


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", type=Path, required=True)
    parser.add_argument("--postgres-url-env", default="SOCRATIC_PARTNER_DATABASE_URL")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    postgres_url = os.environ.get(args.postgres_url_env, "").strip()
    if not postgres_url:
        raise SystemExit(f"{args.postgres_url_env} is required; credentials are never arguments.")
    operation = verify_sqlite_against_postgres if args.verify_only else copy_sqlite_to_postgres
    report = operation(args.sqlite, postgres_url)
    report["source_bytes"] = args.sqlite.stat().st_size
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
