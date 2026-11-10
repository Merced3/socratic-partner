# SQLite → managed Postgres migration

Production durable application/conversation state uses the `socratic` managed
Postgres database through `SOCRATIC_PARTNER_DATABASE_URL`. Alembic migrations
live in `src/socratic_partner/migrations/`; `StateStore.initialize()` applies
them idempotently at startup. Local development and normal CI use temporary
SQLite databases and require no Postgres service.

## Data change and preservation

The initial Postgres migration creates equivalents of SQLite schema 4:
`application_state`, `conversations`, and the one-active-conversation partial
index. Timestamps become UTC `timestamptz`; Discord IDs become 64-bit integers.
The reviewed copy preserves every application-state and conversation value,
including session cards and Pi session metadata. It does not migrate Pi JSONL
transcripts. The harness operational database was deliberately outside P2b's
scope; the later per-host cutover handles it separately as described below.

Pi JSONL files are working memory. Complete open conversations before cutover,
retain source JSONL files read-only, and start future sessions on the new host.
Do not rewrite or synchronize old transcripts merely to resume them elsewhere;
their stored absolute `cwd` is machine-specific. After the initial checksum
verification, archive the historical JSONL files and clear
`application_state.pi_session_id` / `pi_session_file` in Postgres before the
first new process starts. Otherwise Pi attempts to append to the archived file
instead of starting a fresh session.

## Copy and verify

Run from the project with the direct migration endpoint tunneled to localhost,
as documented in ops `DATA.md`. Keep credentials in the environment, never in
command arguments or output. Stop the app first so source counts cannot change.
The destination must be empty: the tool never merges over or replaces rows.

```bash
export SOCRATIC_PARTNER_DATABASE_URL='postgresql://...@127.0.0.1:25432/socratic?sslmode=require'
python -m socratic_partner.migrate_sqlite_to_postgres \
  --sqlite /protected/path/socratic_partner.sqlite3
```

The output contains source bytes and, for each table, source/destination row
counts and deterministic SHA-256 checksums. It contains no row contents.
`--verify-only` repeats the comparison later. A mismatch or nonempty
destination aborts before application cutover.

The optional real-dialect test uses a dedicated empty database/schema:

```bash
export SOCRATIC_PARTNER_TEST_POSTGRES_URL='postgresql://...'
pytest tests/test_postgres.py -v
```

Do not point this test at a populated production database: it creates and
cleans its own fixture rows.

## Harness operational state (per-host cutover follow-up)

Socratic's installed CLI uses `HarnessConfig.from_env()`. Setting
`HARNESS_DATABASE_URL` selects the existing `harness_socratic` managed database
for harness runs, schedules, KV state, and cross-process lease ownership;
`AUTOMATION_HARNESS_DATA_DIR` controls only disposable local files such as
`status.json`. This is independent of application/conversation state in
`socratic`. The P2a harness migration utility performs an idempotent final
source delta copy before the new host starts; no new Socratic schema migration
or duplicate application copy is needed.

Before enabling the URL, preserve the old harness SQLite snapshot and stop the
old process so no second lease/writer exists. Verify run counts/checksums, one
active Postgres lease, health, real Discord behavior, and restart persistence.
If cutover fails before new harness writes, removing the URL returns to the
preserved SQLite configuration; after new Postgres writes, use the harness
merge/recovery evidence rather than discarding them.

## Interruption and rollback

Alembic's schema transaction and the copy transaction each roll back cleanly on
failure. If startup or live acceptance fails before new writes, remove the
Postgres URL from the app environment and start the prior SQLite-based image;
the unchanged read-only source remains available. Back it up before any action
that would make it writable again. If Postgres accepted new conversation
writes, do **not** silently switch back: stop, preserve both sides, and merge
under a newly reviewed recovery plan.

After cutover, retain the SQLite DB and Pi JSONL files unchanged and read-only
until the ops deletion gate (subsequent nightly backup, encrypted dump, restore
drill, read-only interval, and explicit owner approval) is complete.
