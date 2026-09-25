# Needs from automation-harness

**Status: nothing needed currently — all needs met.**

The agent runs as a supervised harness service (`add_service` with a
`ServiceContext`, shutdown via `ctx.stop_event`), same pattern as
discord-hub. Single-instance lock, restart backoff, structured logs, and
`data/status.json` all come from the harness and are sufficient.

## Fulfilled

- Supervised async services with restart-on-failure — in use (entrypoint).
- Graceful stop signaling — the scheduler loop wakes on the stop event
  instead of sleeping through shutdown.

## Watch list (not requests yet)

- Nothing at this time.
