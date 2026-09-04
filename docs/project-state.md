# Project State

## Current revision

- Active branch for accepted product code: `main`
- Current release: `v0.1.0`
- Package version: `0.1.0`
- SQLite schema: version 4
- No `PENDING` state, durable outbox, or scheduler database migration

A commit hash is recorded only when it names a meaningful historical milestone. This file does not try to duplicate the ever-changing `HEAD`; Git remains authoritative for the latest revision.

## Current milestone

v0.1.0 is released. The v0.09 automatic-scheduler milestone is complete, accepted, merged, and soaked.

The product purpose and evidence practice are recorded in [`product-thesis.md`](product-thesis.md). Future directions in [`roadmap.md`](roadmap.md) are outcome hypotheses rather than prescribed implementations.

## Implemented and live-tested

- Guarded Discord guild/channel/user boundary
- Ephemeral controls and persistent conversation messages
- `/status`, `/ask-test`, `/ask-now`, `/done`, `/interval`, `/pause`, and `/resume`
- One restart-recoverable active conversation at a time
- Pi RPC without tools or project resources
- Fresh Pi session for each new conversation
- Provisional session card and completion-relative next activation
- Provider-independent error categories and Pi `stopReason: error` handling
- Public `SocraticApplication` used by manual and automatic kickoff
- Shared non-waiting operation gate with immediate busy feedback
- Default-off automatic scheduler with bounded in-memory backoff
- Opt-in `/test-interval` command hidden during normal use
- Controlled automatic activation, active-conversation suppression, restart recovery, pause/resume, and feature-flag rollback

## Soak result

The one-week normal-use soak ran for over seven days with multiple long-running conversations. The only incident was a transient Discord gateway 503 on 2026-09-03 that discord.py auto-reconnected within ~5 seconds with no user-visible impact. No duplicate activations, no missed questions, and no manual-intervention failures occurred.

## Test status

- Automated suite: 92 passing tests
- Ruff and `git diff --check`: passing at the start of the current documentation milestone
- Public application workflows use real temporary SQLite and controlled ports
- Historical schema fixtures cover versions 1–3 upgrading to version 4
- Cross-platform fake Pi subprocess covers framing, large events, assistant errors, malformed output, timeout/reset, and client reuse
- Scheduler policy, lifecycle, gate, backoff, feature flags, and short intervals have automated coverage
- Real Discord, provider, and process behavior remains bounded manual evidence

See [`../tests/CONTRACTS.md`](../tests/CONTRACTS.md) for the detailed evidence matrix.

## Runtime and rollback

Runtime databases, backups, Pi sessions, logs, credentials, and Discord identifiers remain private and must never be committed.

Automatic scheduling can be rolled back without a database downgrade:

1. Disable automatic scheduling in deployment configuration.
2. Restart the process.
3. Confirm `/status` reports the scheduler disabled.
4. Confirm the manual conversation loop remains available.

Windows autostart is documented in [`setup/windows-autostart.md`](setup/windows-autostart.md).

## Immediate next steps

None. v0.1.0 is the current stable release.

Future work is captured as outcome hypotheses in [`roadmap.md`](roadmap.md).

## Version milestones

- `v0.09`: historical project milestone name for the automatic scheduler; not a release tag
- `v0.1.0`: current stable release and Git tag
- Later releases follow `vMAJOR.MINOR.PATCH`
