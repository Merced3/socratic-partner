# Automatic Scheduler

## Status

Implemented on `feature/automatic-scheduler-v009` and accepted through controlled rollout. The scheduler remains disabled by default and uses SQLite schema version 4 without scheduler-specific persistent state.

## Boundary

The scheduler handles generic timing and activation policy. It does not import Discord, Pi, Socratic prompts, or conversation content. Discord composition supplies:

- Durable state readers
- The shared non-waiting `OperationGate`
- A claimed kickoff operation
- A best-effort failure notification callback

The application validates the scheduler's active lease and runs the same conversation kickoff behavior used by `/ask-now` without trying to acquire the gate twice.

## Eligibility

One kickoff may be attempted when:

- Automatic scheduling is enabled
- Application state is `WAITING`
- `next_question_at` exists and is due in UTC
- No `OPEN` or `CLOSING` conversation exists
- In-memory retry backoff has elapsed
- The shared operation gate can be acquired immediately

Eligibility is checked again after gate acquisition. Manual model operations never wait silently: they either acquire the same gate or receive immediate busy feedback.

## Timing and missed runs

The runtime checks policy at startup and at a bounded 60-second interval. If the process was off past a due time, elapsed intervals coalesce into one kickoff attempt; it does not replay every missed interval. An active conversation suppresses further activation. After `/done`, the next due time is calculated from successful completion.

## Failure policy

- Billing/authentication: application state becomes durably `PAUSED`, the due time is cleared, and one best-effort safe Discord notification is attempted for that failure.
- Rate limit/provider outage/timeout: persisted due time remains unchanged and in-memory exponential backoff prevents a tight retry loop.
- Internal backoff begins at 60 seconds, doubles, and caps at 60 minutes.
- An explicit provider `Retry-After` is never shortened or capped by the internal maximum.
- Notification and retry state are not persisted in v0.1.
- Pi assistant messages ending with `stopReason: error` are never accepted as questions.

Restart clears in-memory backoff, so an overdue activation receives one startup attempt.

## Delivery guarantee

The implementation prevents ordinary duplicate activation within one process but does not claim exactly-once Discord delivery. A small ambiguous crash window remains:

```text
Discord accepts opening question
        ↓
process crashes before SQLite records the conversation
        ↓
restart may post a second opening
```

This accepted v0.1 limitation avoids an unproven durable outbox or `PENDING` conversation state.

## Configuration

```dotenv
SOCRATIC_PARTNER_AUTOMATIC_SCHEDULER_ENABLED=false
SOCRATIC_PARTNER_TEST_CONTROLS_ENABLED=false
```

Missing values default to false and changes require restart.

For a supervised rollout only, enable test controls and use:

```text
/test-interval minutes:1-60
```

After testing, restore `/interval hours:24`, disable test controls, and restart. Disabling the scheduler is the immediate rollback and requires no database migration.

## Controlled rollout evidence

Observed manually on the private deployment:

- Disabled mode preserved the complete manual conversation loop.
- Enabled-but-paused mode produced no activation.
- Automatic activation occurred within the polling window.
- One opening appeared and active-conversation state suppressed later ticks.
- The active conversation survived process restart and retained Pi context.
- Reply and `/done` worked after restart.
- Pause removed the due time; resume established a fresh due time and activated normally.
- Scheduler and test controls disabled cleanly; `/test-interval` disappeared.
- Manual `/ask-test` and `/ask-now` continued to work after rollback.

A forced clean missed-run restart was deferred. Deterministic policy tests cover overdue coalescing; naturally occurring downtime may add live evidence during the soak.

## Process supervision

This scheduler decides when a conversation is due only while the process is running. Windows Task Scheduler, a Windows service, systemd, or another operating-system facility must eventually own startup and process restart.
