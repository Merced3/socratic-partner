# Project State

## Known-good baseline

- Branch: `main`
- Runtime commit: `e92f724 Prevent Pi RPC history timeouts`
- Documentation baseline: `d1034ef Document architecture and development safeguards`
- SQLite schema: version 4
- Scheduler: not implemented and not running
- Automatic activation: not implemented

## Implemented and live-tested

- Guarded Discord guild/channel/user boundary
- Ephemeral control commands
- `/status`, `/ask-test`, `/ask-now`, `/done`, `/interval`, `/pause`, `/resume`
- Persistent normal Discord conversation messages
- One active conversation at a time
- Pi RPC model calls with no tools or project resources
- Fresh Pi session for `/ask-now`
- Conversation recovery after process restart
- Provisional session card on `/done`
- Completion-relative next activation timestamp
- Provider-agnostic error categories
- Detection of Pi assistant `stopReason: error` from authoritative `message_end` events
- Pi RPC recovery after reader/protocol timeout without fetching complete message history
- Billing/authentication failures pause future automation state
- Interval persistence across restart

## Preserved rollback

The abandoned scheduler experiment is retained locally on:

```text
scheduler-experiment-2026-08-26
```

It contains commits `ad9d526` and `827ceae`. Do not merge or cherry-pick it wholesale. It may be consulted for tests or isolated ideas only after review.

## Runtime-data rollback

The scheduler experiment migrated the private runtime database from schema 4 to 7. It was backed up and transactionally returned to schema 4. Non-pending conversation records, application state, session cards, and Pi session references were preserved. Scheduler-only pending/outbox state was removed.

## Test status

- Automated suite at runtime baseline: 39 passing tests
- Manual `/ask-test` and `/ask-now` acceptance passed after the RPC history-timeout fix
- Existing tests predate `tests/README.md` and require incremental rationale/black-box audit

## Next milestone

Design a deliberately small automatic scheduler behind a default-off feature flag. Before implementation, read `docs/automatic-scheduler.md` and obtain explicit approval.

## Definition of v0.09

The project becomes v0.09 when automatic activation is enabled for a controlled soak test and:

- Manual controls still work.
- Restarts do not corrupt an active conversation.
- Missed activation follows the documented policy.
- Failures do not tight-loop or spam Discord.
- Automatic activation can be disabled immediately.

## Definition of v0.1

After v0.09 runs for one week to the user's standards, with documented startup/restart behavior and no unresolved critical reliability issue, the project may be tagged v0.1.
