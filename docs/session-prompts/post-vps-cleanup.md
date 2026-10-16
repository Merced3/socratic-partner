# Session: socratic-partner post-VPS cleanup

**Suggested session name:** `socratic-partner: post-VPS cleanup`

**Gate:** `discord-hub: verification + backlog sweep` (#3) shipped
thread archive/delete (and autocomplete, if it was done). Roadmap:
`Automations/ops/session-prompts/README.md` (#4).

Copy everything below the line into the new session.

---

# Bring socratic-partner's docs up to date with the VPS reality, and use the new hub features

**Read first:** `AGENTS.md`, `docs/README.md`, `docs/project-state.md`,
`docs/roadmap.md`, `docs/development-workflow.md`,
`docs/session-handoff.md`, `tests/CONTRACTS.md`, and the ops `RUNBOOK.md`
(`C:\Users\cedgo\Documents\Coding\Automations\ops\RUNBOOK.md`).
Socrates runs on the droplet now, not the laptop.

## Tasks

1. **Stale docs:** `project-state.md` "Immediate next steps" still says
   to re-enable the Windows `SocraticPartner` scheduled task and add a
   discord-hub task. That's obsolete since the 2026-10-14 VPS move.
   `setup/windows-autostart.md` is now historical. Rewrite "runtime and
   rollback" to point at the ops RUNBOOK. Confirm the laptop scheduled
   task is disabled (otherwise two instances run).
2. **Known limitations the hub now unblocks (tests first):**
   - failed `/ask-now` leaves an empty thread → delete it
   - completed threads aren't archived → archive on completion
   - `/model` autocomplete (only if #3 shipped hub autocomplete routing)
3. **Automatic scheduler:** the doc says "consider enabling." Ask the
   user, and if yes, enable it through the server env (ops
   `env/socratic-partner.env`) and record the decision.
4. Deferred ideas (LLM thread titles, long-term derived memory) stay
   deferred unless the user says otherwise. Note that "long-term derived
   memory from session cards" rhymes with the teaching-agent knowledge-log
   design (#5–#6). Mention it; don't build it.

## Rules

Tests first: agree the tests with the user, stop, approve, then
implement. Update `project-state.md` + `roadmap.md` the same day.

## Success =

The docs describe the real (VPS) runtime; empty-thread and archive
limitations are resolved; the scheduler decision is recorded; tick #4 in
the roadmap.
