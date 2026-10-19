# Project State

## Current revision

- Active branch for accepted product code: `main`
- Current release: `v0.6.1`
- Package version: `0.6.1`
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
- `v0.6.1` — VPS cleanup: failed starts delete empty threads, completed threads archive, `/model` autocomplete works, and docs match the Docker/VPS runtime

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
- Channel registration opts into hub thread deletion, with one-time safe re-registration for pre-existing deployments
- Failed `/ask-now`/automatic kickoff deletes the empty thread it created
- Successful `/done` archives the completed session thread; archive failure does not reopen the completed conversation
- `/model` autocomplete returns bounded authorized choices through discord-hub
- Harness supervision: single-instance lock, restart with backoff, structured logs, `data/status.json`
- Prompt scheduler wakeup on stop; clean Ctrl+C in ~1–2 seconds

## Live acceptance evidence (v0.1.1–v0.6.1)

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

Lab acceptance on 2026-10-19 (`#lab-text`, isolated `/testing` store):

- An intentionally broken Pi executable made `/ask-now` fail; the user received failure feedback and no empty thread remained
- `/model` showed live autocomplete choices
- `/ask-now` created a lab thread, one reply succeeded, and `/done` posted the provisional session card
- The hub archive call returned `200 OK` (`archived=True, locked=False`); Discord hides archived threads from the active list
- `/status` showed `Conversation: none`
- The service was restored to `#reflection`, re-registered that channel with thread-deletion opt-in, returned healthy, and passed a production `/status` smoke check

## Known limitations

- Interaction responses appear as the hub's bot identity (ADR 0003); conversation messages appear as "Socrates"
- Messages sent while the hub is down are missed, not replayed
- The rare Discord-accepted/pre-SQLite duplicate window from v0.1 remains accepted

## Test status

- Automated suite: 135 passing tests
- Ruff and `git diff --check`: passing
- Public application workflows use real temporary SQLite and controlled ports
- The hub client is contract-tested against a protocol-shaped fake; adapter policy is unit-tested
- Real Discord (via hub), provider, and process behavior remains bounded manual evidence

See [`../tests/CONTRACTS.md`](../tests/CONTRACTS.md) for the detailed evidence matrix.

## Runtime and rollback

Production runs on the DigitalOcean/Tailscale VPS as the `socratic-partner` Docker Compose service beside `discord-hub`. The ops [`RUNBOOK.md`](../../../ops/RUNBOOK.md) owns restart, logs, rebuild-from-scratch, backup restore, deploy rollback, secrets handling, and hard-won operational details. Runtime databases, backups, Pi sessions, logs, credentials, and Discord identifiers remain private and must never be committed.

The laptop `SocraticPartner` Task Scheduler entry was confirmed **Disabled** on 2026-10-19, so it will not compete with the VPS instance. Windows autostart documentation is historical.

Rollback for this milestone is a normal VPS service rollback/rebuild from the prior Git revision; no database migration occurred. The one-time hub registration change only opts `#reflection` threads into deletion and remains compatible with the current hub. Automatic scheduling remains disabled by explicit 2026-10-19 user decision; enabling it later is an env change plus service restart.

## Immediate next steps

- Return to normal VPS use with the automatic scheduler disabled
- Treat `#reflection` as production; use `#lab-text` plus `/testing enabled:true` for future Discord acceptance where practical

Deferred ideas (outcome hypotheses, not commitments):

- LLM-generated session-thread titles
- Long-term derived memory from session cards — related in spirit to the teaching-agent knowledge-log sessions (#5–#6), but still not a Socratic Partner build commitment

## Version milestones

- `v0.09`: historical project milestone name for the automatic scheduler; not a release tag
- `v0.1.0`: first stable release and Git tag
- `v0.1.1` … `v0.6.1`: the post-release milestone series (Pi window, `/model`, session threads, harness, hub migration, VPS cleanup)
- `v0.6.0` was tagged briefly but immediately superseded by `v0.6.1` because its runtime `__version__` metadata still said `0.5.0`; use `v0.6.1`
- Later releases follow `vMAJOR.MINOR.PATCH`
