# Development Workflow

## Milestone sequence

```text
Read current state
      ↓
Propose bounded plan
      ↓
Explicit user approval
      ↓
Implement smallest useful slice
      ↓
Automated validation
      ↓
Manual Discord test
      ↓
Process-restart test
      ↓
Commit and push
```

## Plan means pause

If a request says to present a plan before changes, the response containing the plan is the end of that turn. Wait for an explicit approval message before using edit/write tools.

## Automated validation

Follow [`../tests/README.md`](../tests/README.md). User-visible behavior requires a black-box acceptance path; focused integration and unit tests provide supporting failure localization. Every new or modified test must explain why it exists and why it is not coupled unnecessarily to the current implementation.

At minimum:

```powershell
pytest
ruff check .
git diff --check
```

Tests are necessary but not sufficient for Discord delivery, provider behavior, subprocess lifecycle, scheduling, or restart guarantees.

## Live acceptance

Each milestone must document exact manual steps and expected Discord/log output. Do not commit the milestone until the user reports that these steps pass.

## Database migrations

Before adding a migration:

1. Explain the data change in plain language.
2. State what existing records are preserved.
3. Define behavior if migration is interrupted.
4. Define a rollback or compatibility plan.
5. Back up private runtime data before an actual rollback.
6. Test upgrades from the currently deployed schema—not only fresh databases.

## Failure diagnosis

Do not infer root cause solely from a timeout or user-visible symptom. Gather:

- Local application logs
- Pi RPC lifecycle events where available
- Provider error category
- Current durable application state
- Reproduction steps

State uncertainty explicitly when evidence is incomplete.

## Git policy

- Keep `main` at a live-tested state.
- Use a feature branch for autonomous/background behavior.
- Preserve failed experiments on named branches rather than mixing them into `main`.
- Do not force-push shared history.
- Do not commit ignored deployment data.
