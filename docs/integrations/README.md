# Integration contracts

One file per external project this one depends on. Each file is the
*complete* statement of what this project needs from that dependency —
written agnostically, so it can be handed to that project's session as-is.

Rules:

- A file with no open requests says so explicitly: "Nothing needed
  currently — all needs met." Silence is not the same as satisfied.
- Requests are consumer-agnostic: they describe capabilities and reasons,
  never this project's vocabulary (no "Socratic", no "session cards").
- When a request is fulfilled, move it from **Open requests** to
  **Fulfilled** with the date, instead of deleting it — the history
  explains why the dependency does what it does.
- Declined ideas are recorded under **Declined** with the reason, so a
  future session does not re-litigate them.
- If a need appears that belongs to the dependency's general purpose
  (not overfit to us), it goes here, not into our code as a workaround.
