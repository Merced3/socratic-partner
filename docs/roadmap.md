# Roadmap and Transfer Plan

This document preserves the agreed direction across Pi sessions. It distinguishes release requirements from future ideas so development does not become an endless test or architecture project.

## Guiding rules

- Prefer evidence from real use over imagined infrastructure.
- Keep Socratic conversation behavior separate from generic operational scheduling.
- Use Pi for model sessions and reasoning rather than rebuilding an agent runtime.
- Let the operating system keep the process alive; do not build a process supervisor.
- Introduce reusable abstractions only after a second real application proves the shared need.
- Autonomous behavior defaults off until controlled acceptance passes.
- Tests should provide credible evidence, not postpone use indefinitely.
- Plans requiring approval must stop and wait before editing.

## Current position

Current scheduler feature branch:

```text
feature/automatic-scheduler-v009
```

Accepted commits on that branch:

```text
ad61c80  Add non-waiting operation gate
6c7deaf  Add dormant scheduler policy
797ada5  Compose automatic scheduler lifecycle
0976114  Add opt-in short scheduler test interval
```

Current evidence:

- 91 automated tests pass.
- Manual conversation behavior works with scheduling disabled.
- Automatic activation produced one opening within the polling window.
- Active conversations suppressed additional openings.
- An active automatic conversation survived process restart.
- Replies and `/done` worked after restart.
- Pause removed the due time; resume established a fresh due time.
- Scheduler and test controls could be disabled without breaking manual operation.
- The interval was restored to 24 hours.
- SQLite remains schema version 4.
- No `PENDING` state, durable outbox, or scheduler database migration exists.

Accepted limitation for the first release candidate:

- A small ambiguous crash window exists if Discord accepts an opening question but the process crashes before SQLite records the conversation. A rare duplicate after that exact failure is preferable to introducing an unproven distributed outbox in v0.1.

## Immediate completion plan

These are the only remaining steps before the v0.1 development soak. Do not add more forced paid-provider tests unless a new defect supplies a concrete reason.

### 1. Commit short-interval support — complete

The opt-in `/test-interval` control is committed separately and remains hidden unless explicitly enabled.

### 2. Fix the false typing indicator — implemented, pending one live confirmation

The Discord adapter now checks for an open conversation before entering its typing context while retaining application-level validation for race safety. A focused regression test verifies that a message after `/done` does not start typing or make a model call.

### 3. Final scheduler documentation — complete

`README.md`, scheduler behavior, project state, and the contract matrix now describe the accepted implementation and controlled rollout. A forced clean missed-run test was deferred; automated overdue policy exists and real downtime may supply soak evidence.

### 4. Final feature-branch review and merge

Before merge:

- Working tree clean.
- Full tests, Ruff, and `git diff --check` pass.
- Review `main...feature/automatic-scheduler-v009` as a whole.
- Confirm no schema migration, `PENDING`, outbox, or Automation Harness dependency.
- Confirm automatic behavior remains default-off.

Then merge the feature branch into `main` and push. Do not merge the abandoned `scheduler-experiment-2026-08-26` branch.

### 5. Begin the v0.1 development soak

Deployment configuration:

```dotenv
SOCRATIC_PARTNER_AUTOMATIC_SCHEDULER_ENABLED=true
SOCRATIC_PARTNER_TEST_CONTROLS_ENABLED=false
```

Durable application state:

```text
Interval: 24 hours
```

The package version remains `0.1.0.dev0` during the soak. “v0.09” is the project milestone name, not a release tag.

## One-week soak

The soak is normal use, not seven days of continuous scripted testing.

Observe:

- At most one ordinary opening per due activation.
- No opening while paused or while a conversation is active.
- Restart recovery does not corrupt an active conversation.
- `/done` posts and stores a session card and schedules from completion.
- Manual commands return promptly or provide explicit busy feedback.
- Billing/authentication failure pauses future activation.
- Transient failures do not tight-loop or spam Discord.
- Logs contain enough non-private information to diagnose failures.
- Test controls remain disabled.

If a critical problem occurs:

1. Set automatic scheduling to false.
2. Restart.
3. Confirm `/status` reports scheduler disabled.
4. Preserve logs and non-secret error text.
5. Open a narrowly scoped bug-fix session.

A naturally occurring restart after a missed due time can validate catch-up behavior. Do not
extend the soak merely because a forced missed-run test was not performed.

## Keeping the process alive

Automatic scheduling works only while Socratic Partner is running. Before declaring v0.1, choose and document one Windows startup/restart method. Prefer an existing operating-system facility, initially Windows Task Scheduler or a small Windows service wrapper.

This is separate from the internal scheduler:

```text
Windows process supervision
    keeps Socratic Partner running

Socratic scheduler
    decides when a conversation is due
```

Do not make Automation Harness or Socratic Partner reimplement operating-system supervision.

## v0.1 release criteria

Release v0.1.0 when:

- Controlled scheduler rollout passed.
- One-week normal-use soak passed to the user's standards.
- No unresolved critical reliability defect remains.
- A Windows startup/restart procedure is documented and tested.
- `README.md`, project state, scheduler documentation, and contract matrix are current.
- Automatic scheduling can be disabled immediately without data migration.
- Test controls are disabled in the normal deployment.

Release actions:

1. Set package version from `0.1.0.dev0` to `0.1.0`.
2. Run automated validation.
3. Perform a short manual status/start/reply/done smoke test.
4. Commit the release metadata.
5. Tag `v0.1.0`.
6. Push `main` and the tag.

## After v0.1: evidence-driven feature roadmap

The order below is provisional. Re-evaluate it after using v0.1.

### Discord source ingestion

Goal: use existing Discord history as source material without making Discord the canonical database.

Start locally inside Socratic Partner with a clean source boundary:

```text
Discord channel reader
    → normalized records with message ID, timestamps, edits, and provenance
    → local application-owned SQLite
    → Socratic-specific selection and interpretation
```

Initial allowlisted sources may include journal/timeline, mission, ideas, and quotes channels. Channel selection and meaning remain Socratic Partner concerns. Generic retrieval mechanics may be extracted only when another application needs them.

Do not start with a separate ingestion service. Preserve a future seam for one, but avoid an extra process, API, queue, and deployment until independent operation is required.

### Derived memory and review

Keep four concepts separate:

1. Raw source records
2. Conversation history in Pi sessions
3. Derived observations/open questions/contradictions
4. Context selection for a new session

Derived observations should retain source provenance, confidence, and review status. Session cards are provisional rather than unquestionable truth. A future reaction/review workflow may allow acceptance or correction without turning memory maintenance into another daily chore.

### Question selection

Future questions may use ingested evidence, but must not become trapped inside it. Selection should balance:

- Relevant unresolved questions
- Contradictions between stated goals and recent behavior
- Assumptions and tradeoffs
- Occasional questions outside existing source material
- Novel perspectives that improve thinking rather than merely summarize history

Each scheduled conversation should continue to start a fresh Pi session. Relevant structured memory is injected deliberately instead of maintaining one indefinitely growing conversation.

### Cost and model routing

Only add routing after real usage provides cost/quality evidence. Possible later policy:

- Inexpensive model for ordinary conversation and classification
- Stronger model for selecting a high-value opening question
- Stronger model for periodic synthesis when justified

Record usage by operation. Do not build multiple sub-agents merely because the architecture can support them.

### Interaction improvements

Possible features, each requiring its own evidence and milestone:

- Discord threads for conversation isolation
- Session-card reaction/review
- Direct messages
- Voice conversation
- Periodic terminology reinforcement
- Layered explanations from beginner to professional depth
- Knowledge maps and educational handoff

These are not v0.1 requirements.

## Second baseline automation: research and implementation loop

Build the weekly research loop as a separate repository/application after Socratic Partner v0.1 is stable.

Initial goal:

```text
weekly trigger
    → generate candidate ideas
    → cheaply filter weak candidates
    → research a small surviving set
    → publish approximately three ideas
    → record user feedback and outcomes
```

Use existing workflow/orchestration tools where they reduce work. Evaluate Activepieces or Windmill before writing a custom orchestration layer. Expensive models may propose or synthesize; cheaper models may generate/filter, but routing should follow measured costs.

Do not initially add autonomous implementation or self-healing code. Add implementation only after the research/feedback loop proves useful and safety boundaries are explicit.

## When to resume Automation Harness

Automation Harness remains a separate public Phase 0 project. Resume implementation when the second real automation needs a capability already proven in Socratic Partner, such as:

- Persistent due-job evaluation
- Non-waiting operation coordination
- Pi RPC process/session management
- Provider-independent failure policy
- Health/status reporting
- Restart recovery

At that point:

1. Compare both applications' actual requirements.
2. Extract only genuinely shared behavior.
3. Keep prompts, domain state, source meaning, and user-facing templates in each application.
4. Let applications pin versioned harness releases.
5. Do not import the abandoned scheduler experiment wholesale.

The harness may ultimately be a small package, a project template, or documented composition of existing tools. Its value is reliable reuse, not framework size.

## Far-future infrastructure

Defer until evidence requires it:

- Separate ingestion process
- Multiple worker machines
- Central PostgreSQL aggregation
- Durable cross-node outbox synchronization
- Vector database
- Agent-to-agent messaging
- Automatic code implementation/self-healing
- Safe external update supervisor

If multiple nodes later send local SQLite events to centralized PostgreSQL, prefer stable IDs, UTC timestamps, provenance, idempotent writes, and an outbox-based synchronizer. Do not build this for a one-machine v0.1 system.

## Session transfer checklist

A new Pi session should:

1. Read `AGENTS.md`.
2. Read `README.md`, `docs/architecture.md`, `docs/project-state.md`, and this roadmap.
3. Read the document for the requested milestone.
4. Inspect Git branch, status, and recent history.
5. Run tests before changing files.
6. Never read `.env` or private runtime data.
7. Present a bounded plan and stop when approval is required.
8. Preserve accepted work through focused commits and live acceptance.

Use `docs/session-handoff.md` for the full prompt template.
