# Project State

## Current revision

- Active branch for accepted product code: `main`
- Scheduler merge milestone: `91fa20d Merge automatic scheduler v0.09 milestone`
- Current known-good revision: latest live-accepted commit on `main` (see `git log`)
- Package version: `0.1.0.dev0`
- SQLite schema: version 4
- No `PENDING` state, durable outbox, or scheduler database migration

A commit hash is recorded only when it names a meaningful historical milestone. This file does not try to duplicate the ever-changing `HEAD`; Git remains authoritative for the latest revision.

## Current milestone

The v0.09 automatic-scheduler milestone is complete, accepted, and merged. The one-week normal-use soak for v0.1.0 is currently in progress. No critical soak defect has been reported so far.

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

## Controlled rollout result

Observed on the private deployment:

- Disabled scheduling left manual behavior unchanged.
- Enabled-but-paused scheduling produced no question.
- Automatic activation occurred within the 60-second polling window.
- Exactly one opening appeared; later ticks were suppressed by the active conversation.
- An active automatic conversation survived process restart with Pi context intact.
- Replies, `/done`, and session-card generation worked after restart.
- Pause cleared the due time; resume created a fresh due time and automatic activation worked.
- Interval was restored to 24 hours.
- Scheduler and test controls disabled successfully.
- `/test-interval` disappeared when disabled.
- `/ask-test` and the manual conversation loop still worked after rollback.

A forced clean missed-run restart was not required for controlled acceptance. Deterministic tests cover overdue coalescing, and naturally occurring downtime may provide additional evidence during normal use.

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

## Immediate next steps

1. Continue the one-week normal-use soak at the intended 24-hour interval.
2. Keep short test controls disabled during normal use.
3. Record whether the recurring interaction remains useful and unobtrusive—not only whether it remains technically healthy.
4. Adopt and track the validated Windows installation guide.
5. Choose, document, and test a Windows startup/restart procedure before v0.1.0.
6. Correct any stale user-facing or project-state wording discovered during the soak.
7. When release criteria pass, prepare and separately approve the `v0.1.0` release.

## Version milestones

- `v0.09`: historical project milestone name for the automatic scheduler; not a release tag
- `0.1.0.dev0`: current development package version during soak
- `v0.1.0`: next planned release and Git tag after all release criteria pass
- Later releases follow `vMAJOR.MINOR.PATCH`
