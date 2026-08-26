# Working on Socratic Partner

Read `README.md`, `docs/architecture.md`, `docs/project-state.md`,
`docs/development-workflow.md`, `tests/README.md`, and `tests/CONTRACTS.md` before planning changes.

## Approval boundary

When the user asks for a plan, says "before creating/changing anything," or instructs you to
present a plan first:

1. Inspect read-only information needed for the plan.
2. Present the complete plan.
3. Stop and wait for explicit approval.
4. Do not treat presenting the plan as approval to implement it.

## Safety and privacy

- Never read or print `.env`.
- Do not inspect private runtime data unless the user explicitly authorizes a specific operation.
- Never commit secrets, Discord IDs, Pi sessions, logs, or SQLite runtime databases.
- Preserve ignored runtime data across code changes and migrations.
- Back up the database before any migration rollback or destructive operation.

## Development process

Use this sequence for each milestone:

1. Establish the known-good commit and clean working tree.
2. Read the relevant code and documentation.
3. Present a bounded plan and wait for approval when requested.
4. Implement the smallest change that proves the milestone.
5. Run automated tests, Ruff, and `git diff --check`.
6. Confirm user-visible behavior has a black-box acceptance path and every new/modified test
   explains its purpose, regression risk, and resistance to overfitting.
7. Ask the user to perform the documented Discord/restart acceptance test.
8. Commit and push only after live acceptance succeeds.

Do not commit merely because unit tests pass.

## Architecture boundaries

- Socratic Partner owns prompts, conversation behavior, `/done`, session cards, and the meaning of its data.
- Generic scheduling mechanics must not interpret Socratic prompts or conversation content.
- Pi owns model sessions, model calls, compaction, and its tool loop.
- The operating system will eventually own process startup and restart.
- Socratic Partner does not depend on Automation Harness yet.
- Reusable code is extracted only after another real application demonstrates the same need.

## Engineering constraints

- Do not introduce a new persistent state, database migration, background task, or external process without explaining why it is needed and how it rolls back.
- Do not claim an error's root cause without logs, reproduction, or direct evidence.
- Separate required guarantees from desirable guarantees. Explain complexity before attempting exactly-once or distributed-delivery semantics.
- New autonomous behavior must default off until its manual and restart tests pass.
- Manual Discord commands must remain usable and receive clear feedback while background work is active.
- Keep changes reviewable. If a milestone grows unexpectedly, stop and re-plan.
- Follow `tests/README.md`. Unit tests support black-box evidence; they do not replace it.

## Current state

`docs/project-state.md` is the source of truth for the current milestone, known-good commit, schema version, deferred work, and next acceptance criteria. Update it only after a milestone is accepted.
