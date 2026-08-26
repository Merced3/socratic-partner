# Testing Socratic Partner

Tests exist to provide credible evidence that behavior works and remains safe—not to maximize test count or mirror the current implementation.

## Highest-level rule

Every user-visible feature needs a black-box acceptance path.

A black-box test interacts through a public boundary and verifies observable outcomes without assuming how the implementation produced them. For this project, useful boundaries include:

- The installed `socratic-partner` command
- Discord commands/messages through a controlled test adapter
- Pi's newline-delimited RPC protocol through a subprocess boundary
- A temporary SQLite database opened through `StateStore`'s public operations
- Process stop/restart with state inspected through public application behavior

Unit tests and white-box fault injection are allowed as supporting evidence, but they do not replace black-box coverage of the feature they support.

## Test layers

### 1. End-to-end and acceptance tests

Prove a complete user workflow across the application boundary, such as:

```text
start application → invoke /ask-now → receive question → reply → restart → /done → session card
```

Automated end-to-end tests should use controlled local substitutes for paid/unreliable external systems where possible. A smaller opt-in live suite may use the private Discord test deployment and a real model provider, but it must:

- Never run by default in CI
- Never commit or print credentials, Discord IDs, private messages, or runtime data
- Have explicit cost and timeout limits
- Clean up messages/state it creates where practical
- Be documented as live evidence, not a deterministic unit test

### 2. Integration and contract tests

Exercise real boundaries in isolation:

- SQLite migrations against temporary databases
- Pi RPC framing against a fake subprocess/server
- Discord adapter behavior against a fake transport
- Restart recovery using newly constructed application objects

Prefer protocol-shaped fakes over mocks that simply return whatever the implementation expects.

### 3. Unit tests

Use unit tests for pure policy and edge cases such as error classification, timestamp rules, and message formatting. Unit tests should call public functions where practical. Testing a private helper is justified only when the helper owns a critical protocol invariant or fault path that cannot be observed precisely through a public boundary; document that reason.

## Required rationale for every test

Every test must include a concise docstring or an immediately adjacent comment that answers:

1. **Why does this behavior matter?**
2. **What regression or risk does this test detect?**
3. **Why is the assertion not overfit to the current implementation?**

Recommended format:

```python
def test_resume_preserves_interval(tmp_path) -> None:
    """A restart must preserve the user's interval; assert public state, not SQL layout."""
```

For parameterized cases, one test-level rationale may cover the full table when every row proves the same invariant. Do not add repetitive prose to each parameter.

A test name alone is not considered a complete rationale.

## What overfitting looks like

Avoid tests that:

- Duplicate the implementation's branches line by line
- Assert private call order when only the final behavior matters
- Mock every dependency so no real boundary remains
- Assert exact internal SQL/table layout without a migration compatibility reason
- Assert exact wording when semantic content or a structured result is the contract
- Pass only because fixtures reproduce current constants
- Prove that a mock returned its configured value
- Treat code coverage percentage as proof of correctness

Prefer tests that:

- Assert durable state after reconstructing the application
- Exercise malformed, delayed, oversized, or missing protocol messages
- Use fake clocks rather than sleeping
- Use temporary real SQLite databases
- Verify no duplicate observable action when that guarantee is explicitly required
- Check failure recovery and the next valid operation, not only the initial exception

## Maintaining tests as behavior changes

When a test's rationale is no longer true:

1. Decide whether the product contract changed or the test was wrong.
2. Update documentation and acceptance criteria if the contract changed.
3. Replace or remove the obsolete test; do not weaken assertions merely to make it pass.
4. Add coverage for the new behavior and explain its rationale.
5. Preserve tests for fixed regressions when the risk can realistically recur.

Deleting a test is acceptable when its claimed invariant no longer exists and the reason is recorded in the change. Keeping misleading tests is not acceptable.

## Required workflow for a milestone

1. Write or update the black-box acceptance scenario before implementation.
2. Add the smallest lower-level tests needed to localize failures and cover edge cases.
3. Run:

   ```powershell
   pytest
   ruff check .
   git diff --check
   ```

4. Run the documented manual Discord/process-restart acceptance test.
5. Record what passed and what remains untested.
6. Commit only after live acceptance succeeds.

## Current-suite adoption

This policy applies immediately to every new or modified test. Existing tests predate the policy and must be audited incrementally. Do not mass-add meaningless docstrings. When touching an existing test file, improve the rationale and black-box alignment for the tests affected by the change.

Before declaring v0.09, complete a focused audit of all tests and add automated black-box coverage for the full manual conversation loop and restart behavior.

## Honest language

No finite test suite proves that software always works. Use precise claims:

- "This acceptance scenario passed."
- "This regression is covered."
- "This failure mode was simulated."
- "This external path remains manually tested."

Do not say "everything is tested" unless the scope of “everything” is explicitly bounded.
