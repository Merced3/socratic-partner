# Roadmap

## How to read this roadmap

Future plans are expressed as **outcome hypotheses, not prescribed implementations**.

This roadmap is for the user: it preserves what may become valuable and why. It does not preselect technical designs for future models or sessions to execute. Concrete implementation belongs in a separately reviewed milestone plan after current evidence and constraints have been inspected.

Read [`product-thesis.md`](product-thesis.md) first for the longer-lived purpose and documentation practice.

## Current position

The v0.09 automatic-scheduler milestone is complete and merged into `main`. Controlled rollout passed, and the one-week normal-use soak passed with no critical defects. The project is released as v0.1.0.

Evidence established before the soak:

- Manual and automatic conversations work through Discord.
- One automatic opening occurs within the polling window.
- An active conversation suppresses repeated openings.
- An active conversation and its context survive process restart.
- Reply, explicit completion, and provisional session-card behavior work after restart.
- Pause, resume, interval changes, and immediate feature-flag rollback work.
- Test controls can be removed from the visible command set during normal use.
- SQLite remains schema version 4, without scheduler-specific durable state.

Accepted limitation:

- A rare duplicate remains possible if Discord accepts an opening and the process stops before SQLite records the conversation. The current thesis does not justify adding substantial delivery machinery before real use demonstrates that this edge case matters.

## Current outcome hypothesis: useful recurring reflection

**Outcome:** Socrates prompts reflection often enough to recover important threads, but not so often that it becomes noise or pressure.

**Why it may work:** A lightweight external prompt can surface decisions and assumptions that ordinary routines leave unexamined.

**Evidence that supports it:**

- Openings lead to conversations the user considers worthwhile.
- Waiting to answer does not produce duplicate pressure.
- The user continues to choose `/done` and finds the resulting boundary useful.
- The 24-hour rhythm feels sustainable in normal life.

**Evidence that would weaken it:**

- Openings are routinely ignored because they arrive without relevance.
- The interaction becomes an obligation rather than an aid.
- Session cards fail to preserve anything useful.
- Operational maintenance costs more attention than the conversations return.

The one-week soak is normal use, not continuous scripted testing.

Observe:

- whether the prompts are useful and appropriately timed;
- whether only one ordinary opening appears per due activation;
- whether active or paused periods remain quiet;
- whether restarts preserve trust and continuity;
- whether manual controls remain responsive;
- whether failures are understandable and recoverable;
- whether test controls remain disabled.

If a critical problem occurs, disable automatic scheduling, restart, preserve non-secret evidence, and investigate the specific defect rather than broadening the system.

## v0.1.0 release outcome

**Outcome:** A small, dependable personal tool that can run through ordinary weeks without demanding developer supervision.

The release criteria were met:

- the controlled rollout passed;
- the one-week normal-use soak passed to the user’s standards;
- no unresolved critical reliability defect remains;
- Windows startup and restart behavior is documented and tested in [`setup/windows-autostart.md`](setup/windows-autostart.md);
- current documentation matches reality;
- automatic behavior can be disabled immediately without data migration;
- short test controls are disabled during normal use.

Version policy:

- `v0.09` remains the historical name of the scheduler milestone; it is not a release tag.
- `0.1.0.dev0` identified development leading toward the first release.
- The current release and Git tag is `v0.1.0`.
- Future release tags use `vMAJOR.MINOR.PATCH` syntax.

## Future outcome hypotheses

These are possibilities to evaluate, not a queue of promised features.

### Recover the “why” across time

**Outcome:** Returning after days or months should restore the important reasons, unresolved questions, and changes of mind—not merely technical chronology.

**Thesis:** Preserving selected meaning and decision context can reduce repeated explanation and prevent technically correct work from drifting away from its purpose.

**Questions:**

- Which memories genuinely improve the next conversation?
- How should uncertain or outdated observations be represented?
- How can the user correct the record without taking on a maintenance chore?
- When is forgetting healthier than retaining more context?

### Notice patterns in lived evidence

**Outcome:** Socrates helps reveal patterns, tensions, and changes across the user’s existing reflections.

**Thesis:** Connections across journal entries, goals, ideas, and prior conversations may produce better questions than isolated prompts.

**Questions:**

- Which sources does the user actually want considered?
- What counts as evidence rather than interpretation?
- How should provenance and uncertainty remain visible?
- How do we prevent old records from narrowing future possibility?

### Ask better questions, not merely more informed ones

**Outcome:** Openings become more relevant and surprising while retaining the ability to introduce perspectives outside recorded history.

**Thesis:** Useful questioning requires a balance between continuity, contradiction, novelty, and the user’s current attention.

**Evidence of value:** The user more often recognizes a real decision, assumption, or possibility that had not been clearly seen before.

### Make reflection easier to review and correct

**Outcome:** The user can accept, reject, or refine provisional conclusions without turning reflection into administration.

**Thesis:** Trust grows when summaries remain correctable and clearly provisional.

### Improve accessibility of the interaction

**Outcome:** Socratic reflection fits more naturally into the situations where the user thinks best.

Possible experiences worth evaluating include conversation isolation, voice, private interaction, terminology reinforcement, layered explanation, and educational handoff. No interface should be selected until its intended human benefit is clear.

### Keep quality and cost proportionate

**Outcome:** The system provides worthwhile reflection at a cost the user understands and accepts.

**Thesis:** Different moments may justify different levels of reasoning effort, but added complexity is valuable only if measured use shows a meaningful quality or cost improvement.

## A second useful automation

**Outcome:** Build another automation that produces an independent, recurring benefit—currently imagined as a research-and-ideas loop—without making Socrates responsible for unrelated work.

**Thesis:** A second real application will reveal which operational lessons are genuinely reusable and which are specific to Socratic conversation.

Potential value to test:

- a manageable number of worthwhile ideas rather than a flood;
- research that improves decisions rather than merely producing summaries;
- feedback that changes what the system explores next;
- a weekly rhythm that remains useful without supervision.

## When Automation Harness matters

Automation Harness should resume when it can improve a demonstrated outcome for at least two real applications.

The outcome hypothesis is:

> A second useful automation should take less time and be safer to operate because lessons proven in the first automation can be reused.

Evidence for resuming it would be repeated operational friction or duplicated proven behavior across Socrates and another application. Its purpose is reliable reuse, not framework growth. Do not expand it solely because abstraction is technically possible.

## Long-horizon possibilities

Larger infrastructure, multiple machines, centralized memory, autonomous implementation, and self-healing behavior remain possibilities rather than plans. They should enter a milestone only when a concrete human outcome cannot be achieved safely and simply without them.

## Session continuity checklist

A future development session should:

1. Read `AGENTS.md` and [`product-thesis.md`](product-thesis.md).
2. Read `README.md`, `architecture.md`, `project-state.md`, and this roadmap.
3. Inspect Git state and the evidence for the requested milestone.
4. State the outcome and thesis before proposing implementation.
5. Separate current technical constraints from future possibilities.
6. Stop for approval when required.
7. Preserve accepted evidence without committing private runtime data.
