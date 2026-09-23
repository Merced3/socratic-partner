# Project State

## Current revision

- Active branch for accepted product code: `main`
- Current release: `v0.5.0`
- Package version: `0.5.0`
- SQLite schema: version 4 (unchanged since v0.1.0)
- No `PENDING` state, durable outbox, or scheduler database migration

A commit hash is recorded only when it names a meaningful historical milestone. This file does not try to duplicate the ever-changing `HEAD`; Git remains authoritative for the latest revision.

## Current milestone

The post-v0.1.0 milestone series is complete and live-accepted:

- `v0.1.1` — the Pi subprocess no longer opens a console window on Windows
- `v0.2.0` — `/model` switches the reasoning model live, in any conversation state
- `v0.3.0` — each session lives in its own thread under the configured home channel
- `v0.4.0` — automation-harness owns the process lifecycle (lock, supervision, logs, `status.json`)
- `v0.5.0` — all Discord interaction moved to discord-hub; socratic-partner contains no Discord library and holds no Discord credentials

The product purpose and evidence practice are recorded in [`product-thesis.md`](product-thesis.md). Future directions in [`roadmap.md`](roadmap.md) are outcome hypotheses rather than prescribed implementations.

## Implemented and live-tested

- Channel/user authorization boundary enforced project-side (ADR 0003); guild boundary is a discord-hub deployment property
- Ephemeral controls and persistent conversation messages via the hub
- `/status`, `/ask-test`, `/ask-now`, `/done`, `/interval`, `/pause`, `/resume`, `/model`
- One restart-recoverable active conversation at a time, hosted in its own thread
- Pi RPC without tools or project resources; hidden console window on Windows
- Fresh Pi session for each new conversation
- Provisional session card and completion-relative next activation
- Provider-independent error categories and Pi `stopReason: error` handling
- Textless Pi responses rejected with diagnosable metadata (stopReason, content shape)
- Shared non-waiting operation gate with immediate busy feedback
- Default-off automatic scheduler with bounded in-memory backoff
- Opt-in `/test-interval` command hidden during normal use
- Harness supervision: single-instance lock, restart with backoff, structured logs, `data/status.json`
- Prompt scheduler wakeup on stop; clean Ctrl+C in ~1–2 seconds

## Live acceptance evidence (v0.1.1–v0.5.0)

Performed by the user against the private deployment with discord-hub running:

- Startup registers the home channel and synchronizes 8 commands through the hub
- Single-instance lock refuses a second copy; harness backoff recovers a down hub automatically
- `/status`, `/ask-test` answer ephemerally
- `/ask-now` creates a `Session <UTC timestamp>` thread; the opening question arrives as "Socrates"
- Replies in the thread show typing and are delivered as replies; **no Pi console window appears**
- Messages outside the active thread are ignored; messages inside reach the model
- `/done` posts the provisional session card in the thread
- Permission preflight blocked a paid operation when the hub bot lacked View Channel, and named the missing permission
- Ctrl+C during an active conversation stops cleanly; restart recovers the conversation with context

## Known limitations

- A failed `/ask-now` may leave one empty thread (the hub has no thread delete endpoint yet)
- Completed threads are not archived (the hub has no archive endpoint yet)
- `/model` has no autocomplete (the hub does not route autocomplete yet); empty value lists models
- Interaction responses appear as the hub's bot identity (ADR 0003); conversation messages appear as "Socrates"
- Messages sent while the hub is down are missed, not replayed
- The rare Discord-accepted/pre-SQLite duplicate window from v0.1 remains accepted

## Test status

- Automated suite: 103 passing tests
- Ruff and `git diff --check`: passing
- Public application workflows use real temporary SQLite and controlled ports
- The hub client is contract-tested against a protocol-shaped fake; adapter policy is unit-tested
- Real Discord (via hub), provider, and process behavior remains bounded manual evidence

See [`../tests/CONTRACTS.md`](../tests/CONTRACTS.md) for the detailed evidence matrix.

## Runtime and rollback

Runtime databases, backups, Pi sessions, logs, credentials, and Discord identifiers remain private and must never be committed. Discord credentials now live only in discord-hub's `.env`; socratic-partner's `.env` holds identifiers and local endpoints only.

Rollback remains: revert the merge to return to `v0.1.0`; no database migration occurred. Automatic scheduling can still be disabled via configuration without a downgrade.

Windows autostart is documented in [`setup/windows-autostart.md`](setup/windows-autostart.md). Note that `discord-hub` must also run for Socratic Partner to function; the harness retries until the hub appears.

## Immediate next steps

- Re-enable the `SocraticPartner` scheduled task against updated `main`; add a `discord-hub` task
- Return to normal use; consider enabling the automatic scheduler

Deferred ideas (outcome hypotheses, not commitments):

- LLM-generated session-thread titles
- Hub support for thread delete/archive and command autocomplete
- Long-term derived memory from session cards

## Version milestones

- `v0.09`: historical project milestone name for the automatic scheduler; not a release tag
- `v0.1.0`: first stable release and Git tag
- `v0.1.1` … `v0.5.0`: the post-release milestone series (Pi window, `/model`, session threads, harness, hub migration)
- Later releases follow `vMAJOR.MINOR.PATCH`
