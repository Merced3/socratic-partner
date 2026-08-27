# Project State

## Current revision

- Active branch: `feature/automatic-scheduler-v009`
- Main baseline: `e2c7c0a Update project state after boundary tests`
- Latest accepted feature commit: `0976114 Add opt-in short scheduler test interval`
- Uncommitted finalization: post-`/done` typing fix and release documentation
- SQLite schema: version 4
- No `PENDING` state, durable outbox, or scheduler database migration

## Implemented and live-tested

- Guarded Discord guild/channel/user boundary
- Ephemeral control commands and persistent conversation messages
- `/status`, `/ask-test`, `/ask-now`, `/done`, `/interval`, `/pause`, `/resume`
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

Slice D completed with the following evidence:

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

A forced clean missed-run restart was intentionally deferred. Deterministic tests cover overdue coalescing, and naturally occurring downtime may provide additional soak evidence.

## Test status

- Automated suite including the final typing regression: 92 passing tests
- Public application workflow covers start, reply, reconstruction, continuation, completion,
  session-card storage, and next-interval timing with real temporary SQLite
- Historical schema fixtures cover versions 1–3 upgrading to version 4
- Cross-platform fake Pi subprocess covers framing, oversized events, assistant errors,
  malformed output, timeout/reset, and client reuse
- Scheduler policy, lifecycle, gate, backoff, feature flags, and short intervals are automated
- Real Discord/provider/process behavior remains bounded manual acceptance

See `tests/CONTRACTS.md` for the detailed evidence matrix.

## Preserved experiments and backup

The abandoned scheduler experiment remains on local branch:

```text
scheduler-experiment-2026-08-26
```

Do not merge or cherry-pick it wholesale. A pre-rollout database backup exists in ignored runtime storage. Runtime databases and backups must never be committed.

## Immediate next steps

1. Validate the post-`/done` typing-indicator fix locally and once through Discord.
2. Run the full suite, Ruff, and `git diff --check`.
3. Review `main...feature/automatic-scheduler-v009` as a whole.
4. Commit finalization and push the feature branch.
5. Merge the accepted feature branch into `main` and push.
6. Configure 24 hours, scheduler enabled, and test controls disabled.
7. Begin the one-week normal-use soak described in `docs/roadmap.md`.

## Version milestones

- Development soak: package remains `0.1.0.dev0`; “v0.09” is a project milestone, not a tag.
- v0.1.0: tag only after the one-week soak, a tested Windows startup/restart procedure, current documentation, and no unresolved critical reliability defect.
