# Product Thesis

## Why this project exists

Socratic Partner exists to help one person think more clearly over time. Its value is not that it can generate messages on a schedule. Its value is that it can interrupt drift, challenge assumptions, expose tradeoffs, and turn vague concerns into decisions or better questions.

The desired outcome is:

> Regular conversations that help the user recover the thread of what matters, understand why a direction was chosen, and make deliberate progress without becoming trapped in technical detail.

## The problem behind the product

Good ideas often arrive with a vivid reason and sense of possibility. During long implementation periods, documentation tends to preserve technical facts more faithfully than it preserves that original reason. The project can then remain technically coherent while its human purpose fades from view.

When the “why” is lost:

- implementation starts to feel like an end in itself;
- confidence falls because progress is hard to connect to a useful outcome;
- models optimize the visible technical trail instead of the intended human result;
- new possibilities are judged against old implementation choices rather than the underlying goal;
- the user has to reconstruct motivation from memory.

This project should preserve purpose as deliberately as it preserves architecture.

## Documentation longevity practice

Every substantial direction should retain four things:

1. **Outcome** — What should become better for the user or the world?
2. **Thesis** — Why do we believe this direction could produce that outcome?
3. **Evidence** — What observation would strengthen or weaken that belief?
4. **Decision history** — Why was this path chosen over realistic alternatives at the time?

Technical plans may change without invalidating the outcome. When implementation changes, update technical documentation first; change the thesis only when the underlying belief or desired outcome changes.

Before beginning a milestone, ask:

- Which outcome does this serve?
- What are we trying to learn?
- What would make us stop, simplify, or choose another path?

After completing a milestone, record:

- what happened in real use;
- what was learned about the thesis;
- whether the next outcome still matters;
- which technical decisions are temporary rather than part of the purpose.

## Roadmap rule

Future plans are expressed as **outcome hypotheses, not prescribed implementations**.

The roadmap belongs to the user. It should describe desired changes in lived experience, why they may matter, and how their value could be recognized. It should not lock future sessions into databases, services, model arrangements, frameworks, or other technical choices before evidence makes those choices necessary.

Architecture documents may preserve current technical boundaries. Milestone plans may propose concrete implementation after inspection and approval. Neither should silently redefine the product thesis.

## Current thesis under test

A lightweight, recurring Socratic conversation can be more useful than waiting for the user to notice when reflection is needed. The interaction should remain easy to pause, easy to resume, and subordinate to the user’s attention rather than becoming another source of pressure.

Current evidence:

- Manually initiated conversations are useful and recover across restart.
- Automatic activation can create one timely opening without repeated prompts while a conversation is active.
- The user can reply when ready rather than immediately.
- Explicit completion creates a useful boundary and schedules the next opportunity from that point.
- Immediate rollback preserves trust in the automation.

The one-week normal-use soak is testing whether this remains useful and unobtrusive outside a controlled rollout.

## Stewardship

This file is intentionally short enough to reread. `AGENTS.md` requires future development sessions to read it before planning changes.

For another project, preserve the same practice in that project’s own thesis document rather than copying Socratic Partner’s conclusions. A reusable template may be kept separately, but each project must state its own outcome, thesis, evidence, and decision history close to the work it governs.
