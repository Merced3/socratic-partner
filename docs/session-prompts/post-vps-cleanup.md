# Session: socratic-partner post-VPS cleanup

**Suggested session name:** `socratic-partner: post-VPS cleanup`

**Status:** ✅ complete — 2026-10-19

**Gate:** `discord-hub: verification + backlog sweep` (#3) shipped
thread archive/delete (and autocomplete, if it was done). Roadmap:
`Automations/ops/session-prompts/README.md` (#4).

Copy everything below the line into the new session.

*Mark this top section as complete when done. Don't edit the instructions below for audit purposes.*

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

---

*When done. Anotate everything that was done below. include anything that you think should be known aswell.*

## Outcome — 2026-10-19

Completed and live-accepted.

### Code

- Added hub `archive_thread`, channel deregistration, and channel registration support for `allow_thread_deletion`.
- Startup now upgrades a pre-existing Socrates channel registration that lacks thread-deletion opt-in by deregistering and re-registering it. This ran cleanly on `#reflection` (`204` then `201`).
- Failed `/ask-now` now deletes the empty thread it created when Pi, message delivery, or durable persistence fails. Thread-creation failure itself has no thread ID to delete and remains a clear user-facing failure.
- Automatic scheduler kickoff uses the same failed-start cleanup path.
- Successful `/done` archives the completed session thread. Archive failure is logged and reported as manual cleanup, but does not reopen or corrupt the completed conversation.
- `/model` now declares hub autocomplete and returns authorized, filtered, max-25 choices; Pi/listing failure returns an empty choice list rather than leaving Discord waiting.
- Package version moved to `0.6.1`. (`v0.6.0` was tagged briefly, then superseded because runtime `__version__` metadata had been missed and still reported `0.5.0`.)

### Tests and validation

- Added contract/adapter tests for failed-start deletion, delivery/persistence failure cleanup, automatic kickoff cleanup, archive success/failure, registration opt-in/re-registration, autocomplete filtering/limit/failure/authorization, and hub wire payloads.
- Automated validation: **135 passed**, Ruff passed, `git diff --check` passed. A packaging regression test now keeps `socratic_partner.__version__` aligned with `pyproject.toml`.
- Live lab acceptance used `#lab-text`, not `#reflection`, with `/testing enabled:true`:
  - with Pi intentionally misconfigured, `/ask-now` failed cleanly and left no empty thread;
  - `/model` showed live autocomplete choices;
  - `/ask-now` opened a session thread, a reply worked, and `/done` posted the provisional card;
  - hub logs showed `POST /threads/{id}/archive -> 200 OK`, `archived=True locked=False`;
  - `/status` showed no active conversation.
- Discord hides archived threads from the active thread list; the user initially could not see an explicit archived marker, but the hub API/log evidence confirms the archive succeeded.
- Production was restored to `#reflection`, health passed, and `/status` there passed.

### Runtime/docs decisions

- The laptop `SocraticPartner` scheduled task is **Disabled**, so the old Windows instance will not compete with the VPS.
- The user chose to keep `SOCRATIC_PARTNER_AUTOMATIC_SCHEDULER_ENABLED=false` on the VPS. Manual `/ask-now` remains the only activation path.
- `setup/windows-autostart.md` is now explicitly historical; the ops `RUNBOOK.md` is the production runtime/rollback source.
- `docs/integrations/discord-hub.md` now records that the previously open thread-deletion request is met; no hub requests remain open for Socratic Partner.
- Deferred ideas remain deferred: LLM session-thread titles and long-term derived memory. The latter rhymes with the teaching-agent knowledge-log design (#5–#6), but was not built here.

### Operational notes

- The updated code was temporarily patched onto the VPS for lab acceptance before commit because the deployment pipeline builds from the server clone. After acceptance, the server clone was reset to pushed `main`, rebuilt, and redeployed from `abcf6ee` (`v0.6.1`).
- Final pushed commits: `c96fd8f` (feature/docs), `abcf6ee` (runtime version metadata fix, tagged `v0.6.1`), and ops `855dc3c` (roadmap #4 tick).
- GitHub CI passed for both project pushes/tags; the ops deploy workflow passed for the roadmap tick.
- Final VPS verification: `socratic-partner` healthy, runtime version `0.6.1`, and `SOCRATIC_PARTNER_AUTOMATIC_SCHEDULER_ENABLED=false`.
- The one-service Docker rebuild succeeded and did not rebuild other services.
- `#reflection` is back in production configuration; the lab registration remains available for future tests.
- Ops roadmap item #4 was ticked in `Automations/ops/session-prompts/README.md`.
