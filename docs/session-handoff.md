# Session Handoff

Use this when beginning a fresh Pi development session.

## Suggested session name

```text
socratic-partner-<milestone>
```

## Prompt template

```text
Continue development of Socratic Partner in:

C:\Users\merce\Documents\Pi-Work-Station\socratic-partner

Before planning or changing files:

1. Read AGENTS.md completely and follow its approval boundary.
2. Read README.md, docs/product-thesis.md, docs/architecture.md, docs/project-state.md, docs/roadmap.md, docs/development-workflow.md, and the document for the requested milestone.
3. Inspect recent Git history and confirm the working tree/branch.
4. Run the existing tests.
5. Never read .env or expose private runtime data.

Requested milestone: <describe one milestone>

First perform read-only inspection. Then present:

- Current-state summary
- Assumptions and unresolved decisions
- Smallest proposed implementation
- Exact files to change
- Database impact and rollback plan
- Automated and live acceptance tests

STOP after presenting the plan. Do not edit files, create files, commit, or push until I send a separate explicit approval message.
```

## Closing a session

Before ending a development session:

- Ensure accepted work is committed and pushed.
- Record the latest known-good commit in `docs/project-state.md`.
- Record deferred work, unresolved risks, and the outcome hypothesis behind the next direction.
- Include exact acceptance-test results.
- Start a new session at a milestone boundary rather than relying indefinitely on compacted conversational context.
