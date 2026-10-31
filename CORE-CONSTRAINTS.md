# Core constraints — paths and rules where changes stay human-reviewed

Everything listed here is load-bearing for what Socratic Partner IS.
Automated agents may propose changes in discussion, but merges touching
these paths always require the owner's explicit code-owner approval.

## Product and conversation ownership

- Socratic Partner owns its prompts, conversation behavior, `/done`,
  session cards, and the meaning of its data. Generic transport, runtime,
  and scheduling machinery must not interpret its prompts or content.
- Preserve the product thesis and the human outcome. A technical refactor
  must not silently redefine the product direction.
- Pi owns model sessions and tool loops; Discord remains an adapter through
  discord-hub. Reusable machinery is extracted only on demonstrated need.

Guardian files for this boundary:

- `AGENTS.md`
- `docs/product-thesis.md`, `docs/architecture.md`, and
  `docs/project-state.md`
- `src/socratic_partner/` — prompts, conversation policy, persistence,
  scheduling, operation gates, and consumer contracts

## Privacy, state, autonomy, and deploy safety

- Learner conversations and runtime databases are private. Never commit
  secrets, Pi sessions, logs, Discord IDs, or SQLite runtime data.
- Back up before destructive migrations or rollbacks; preserve ignored
  runtime data. New persistent state or background work needs an explicit
  rollback story.
- New autonomous behavior defaults off until manual and restart tests pass;
  billing/authentication failures pause autonomy.
- `.github/` — CI, Dependabot, and auto-merge wiring.
- `pyproject.toml` — runtime dependencies and packaging.

## Rule of thumb

If a change exposes learner data, weakens evidence about behavior, silently
changes Socratic policy, adds unattended work, or risks durable state, it
belongs to a human-reviewed change.
