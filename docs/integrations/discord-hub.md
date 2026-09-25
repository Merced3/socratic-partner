# Needs from discord-hub

**Status: one open request (thread deletion). Everything else is met.**

Hand this file to a discord-hub session. Every request is written agnostically:
the hub serves any project; no consuming project's vocabulary appears in the
contracts. Reasons and example consumers are given so the hub session can
judge the design, not just the ask.

Principle the hub already follows, restated for alignment: the hub owns the
Discord connection and Discord primitives. Projects own their own databases,
their own session/thread meaning, and their own cleanup logic. The hub must
never need to know what a "session" or a "conversation" is.

---

## Open requests

### 1. Thread deletion primitive (for test-session cleanup)

- `DELETE /threads/{thread_id}` (or `POST /threads/{thread_id}/delete`) —
  delete a thread the bot can manage.

**Reason:** projects run test sessions constantly during development. The
desired flow is owned ENTIRELY by the consuming project: the user runs a
cleanup command → the project deletes its own database rows and local state
→ the project calls the hub to delete the Discord thread. The hub's part is
only the Discord-side deletion primitive; it stays agnostic of what a
session is.

**Consumers:** this project (cleanup command already built against this
contract — it degrades to "delete the thread manually" while the endpoint
is absent, so there is no urgency), teaching-agent (same pattern, requested
in its own integrations file). Two independent consumers want the same
primitive, which is the hub's bar for a general-purpose feature.

## Declined (recorded so the idea is not re-litigated)

- **Larger message character limits via a paid Discord tier.** A consumer
  considered conforming its output sizing to an "upgraded" plan. Discord's
  ~2000-character cap applies to bot and webhook messages regardless of any
  user/server subscription, so there is no effective limit for the hub to
  report and nothing to conform to. If Discord ever does vary the limit by
  send path, the right shape would be a capabilities endpoint
  (`GET /channels/{id}/limits`) — reopen only if that becomes real.

## Already exists, no work needed

`POST /messages` (chunking, replies, webhook identity), `POST /threads`,
`PUT /commands` (routing, defer, followups), channel registrations with
inbound callbacks and thread inheritance, typing indicators, permission
preflight, harness integration. This project's entire text surface is
covered by the current contract.
