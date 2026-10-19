# Needs from discord-hub

**Status: all current requests are met.** There is no open integration request.

Hand this file to a discord-hub session when changing the shared boundary. Every
request is written agnostically: the hub serves any project; no consuming
project's vocabulary appears in the contracts. Reasons and example consumers are
given so the hub session can judge the design, not just the ask.

Principle the hub follows, restated for alignment: the hub owns the Discord
connection and Discord primitives. Projects own their own databases, their own
session/thread meaning, and their own cleanup logic. The hub must never need to
know what a "session" or a "conversation" is.

---

## Met requests this project relies on

- `POST /messages` — send/chunk project conversation text and replies.
- `POST /threads` — create one public thread per session.
- `DELETE /threads/{thread_id}` — delete a thread when the parent registration
  opted in with `allow_thread_deletion: true`.
- `POST /threads/{thread_id}/archive` — archive or unarchive a thread without
  deleting its history.
- `POST /registrations` and `DELETE /registrations/{channel_id}` — claim a
  channel, route inbound callbacks, establish webhook identity, and safely
  re-register when the thread-deletion opt-in changes.
- `PUT /commands` — route project-owned slash commands, deferred responses,
  followups, and option autocomplete.
- `GET /channels/{channel_id}/permissions` — preflight delivery permissions
  before paid model work.
- Typing indicators, thread inheritance for inbound messages, and hub uptime /
  timeout distinctions.

## Current project-side behavior

- Socratic Partner registers `#reflection` with `allow_thread_deletion: true`.
- A failed `/ask-now` or automatic kickoff deletes only the empty thread it
  just created.
- Successful `/done` archives the completed session thread; archive failure is
  reported but does not reopen the completed conversation.
- `/model` declares autocomplete and answers through the hub callback with at
  most 25 authorized choices.
- `/delete-session` remains the explicit test-cleanup command for removing
  local state plus the Discord thread.

## Declined (recorded so the idea is not re-litigated)

- **Larger message character limits via a paid Discord tier.** A consumer
  considered conforming its output sizing to an "upgraded" plan. Discord's
  ~2000-character cap applies to bot and webhook messages regardless of any
  user/server subscription, so there is no effective limit for the hub to
  report and nothing to conform to. If Discord ever does vary the limit by
  send path, the right shape would be a capabilities endpoint
  (`GET /channels/{id}/limits`) — reopen only if that becomes real.
