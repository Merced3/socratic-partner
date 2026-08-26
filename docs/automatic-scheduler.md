# Automatic Scheduler Milestone

## Status

Not implemented. The previous experiment was rolled back before publication because its scope and guarantees grew beyond what had been reviewed or live-tested.

## Goal

When automatic scheduling is explicitly enabled, start one new Socratic conversation after the persisted activation time becomes due.

## Plain-language recommended defaults

The user does not need to choose distributed-systems terminology unaided. Use these initial policies unless real usage demonstrates a need to change them.

### Delivery guarantee

Prefer a small, understandable implementation over a claim of perfect exactly-once delivery. Only one scheduler task runs in one process. It should prevent ordinary duplicate activation, but v0.09 may document a very small ambiguous crash window between Discord accepting a message and SQLite recording it.

Do not introduce a durable outbox or a new `PENDING` conversation state without separate review and approval.

### Missed run

If the computer was off when a question became due, ask once after startup. Do not generate one question for every missed interval. The next interval begins when that conversation is closed.

### Default state

Automatic scheduling defaults **off** behind a configuration feature flag. Manual `/ask-now` continues to work. Enable the scheduler only for the controlled v0.09 soak test.

### Manual priority

If a manual command and automatic activation collide, return a clear busy response or allow the manual action to win before model generation begins. Never silently ignore a manual command.

### Pi contention

Only one Pi model run may execute at a time. A background activation must not make `/ask-test`, `/done`, or a conversation reply appear hung without explanation. Expose busy state and bound waits. Do not diagnose contention without logs.

### Failure behavior

- Billing/authentication: pause automatic scheduling and notify once after confirmed delivery.
- Rate limit/provider outage: use bounded backoff and no tight retry loop.
- Unknown failure: preserve manual controls and report through status/logs.
- Never treat a Pi assistant error as a successful question.

### Rollout

1. Implement behind a default-off flag.
2. Test scheduler logic with a fake clock and fake kickoff operation.
3. Verify manual behavior with the flag off.
4. Enable a short interval in the private test deployment.
5. Test restart before due, after due, and during an active conversation.
6. Restore the intended 24-hour interval.
7. Begin the one-week v0.09 soak test.

### Rollback

Disabling the feature flag must restore manual-only operation without a database downgrade. Prefer no schema change for the first scheduler slice. If a migration becomes necessary, stop and obtain approval with a separate rollback plan.

## Required code boundary

Refactor kickoff into one application operation used by `/ask-now` and the scheduler. The scheduler calls that operation but does not import or interpret Socratic prompt text.

The first implementation plan must identify exact files and tests, then stop for approval.
