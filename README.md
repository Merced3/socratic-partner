# Socratic Partner

A personal conversational AI designed to challenge assumptions, expose tradeoffs, and help clarify decisions without optimizing for either validation or disagreement.

## Current status

The v0.09 automatic-scheduler milestone is complete, merged, and passed a one-week normal-use soak. The project is released as v0.1.0.

Implemented:

- Environment-based configuration
- Explicit guild, channel, and user allowlisting
- Discord application-command registration
- Private `/status`, `/ask-test`, `/ask-now`, `/done`, `/interval`, `/pause`, and `/resume` controls
- Normal persistent Discord messages for Socratic conversations and session cards
- One restart-recoverable active conversation at a time
- Versioned Socratic behavior, opening, and session-card prompts
- SQLite schema migration and durable `WAITING`/`PAUSED` state
- Persisted interval and planned next-activation timestamp
- Isolated Pi RPC process with no tools or project resources
- Persistent Pi session metadata and model usage records
- Provider-agnostic billing, authentication, rate-limit, availability, and timeout errors
- Detection of Pi assistant messages ending with `stopReason: error`
- Automatic pause after billing or authentication failures
- Optional model-suggested stopping points without automatic closure
- Structured local logs
- Clean scheduler, Pi, and Discord shutdown
- Default-off automatic activation with completion-relative timing and missed-run coalescing
- Immediate busy feedback for competing model operations
- Bounded in-memory retry backoff without shortening provider `Retry-After`
- Opt-in short interval control for supervised testing

Not implemented yet:

- Discord source ingestion or long-term derived memory
- Automatic conversation completion
- Threads, reactions on session cards, or direct messages

## Requirements

- Python 3.11 or newer
- A private Discord server
- discord-hub running locally (it owns the Discord connection)

## Install for development

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ../automation-harness  # not on PyPI; install from sibling
python -m pip install -e ".[dev]"
```

The automation-harness owns the process lifecycle: single-instance lock,
graceful shutdown, supervised restart with backoff, structured logs, and
`data/status.json`. Socratic Partner runs as a supervised service inside it.

## Configure

Discord credentials, reconnect logic, and the bot itself belong to
[discord-hub](../discord-hub) — Socratic Partner holds no token and imports
no Discord library. Set up and run the hub first, then create a private
home channel (for example `#reflection`) that will host one thread per
session. The hub's bot needs these permissions in that channel: View
Channel, Send Messages, Read Message History, Create Public Threads, and
Send Messages in Threads.

Enable Discord Developer Mode to copy the home channel and your user IDs.

Copy the configuration template:

```powershell
Copy-Item .env.example .env
```

Fill in `.env` locally:

```dotenv
DISCORD_TEST_CHANNEL_ID=your-home-channel-id
DISCORD_ALLOWED_USER_ID=your-user-id
SOCRATIC_PARTNER_HUB_URL=http://localhost:8100
SOCRATIC_PARTNER_CALLBACK_HOST=127.0.0.1
SOCRATIC_PARTNER_CALLBACK_PORT=9100
SOCRATIC_PARTNER_TEST_MODE=true
SOCRATIC_PARTNER_TEST_CONTROLS_ENABLED=false
SOCRATIC_PARTNER_AUTOMATIC_SCHEDULER_ENABLED=false
SOCRATIC_PARTNER_DATABASE_PATH=data/socratic_partner.sqlite3
SOCRATIC_PARTNER_DEFAULT_INTERVAL_HOURS=24
SOCRATIC_PARTNER_PI_EXECUTABLE=pi
SOCRATIC_PARTNER_PI_SESSION_DIRECTORY=data/pi-sessions
SOCRATIC_PARTNER_PI_MODEL=
SOCRATIC_PARTNER_PI_TIMEOUT_SECONDS=120
SOCRATIC_PARTNER_LOG_LEVEL=INFO
```

`.env` and runtime data are ignored by Git. On startup, Socratic Partner
registers the home channel with the hub (its messages arrive as `Socrates`
via the channel webhook) and publishes its slash commands through the hub.

## Run

```powershell
socratic-partner
```

When connected, use `/ask-now` to open a session thread with the first Socratic question. Reply normally inside that thread, then use `/done` to generate a provisional session card and close the conversation. Use `/interval` to set 1–720 hours between completed conversations, and `/model` to switch the reasoning model at any time. Control-command responses remain ephemeral; conversation messages and session cards remain visible in the thread. Automatic scheduling is opt-in. `/test-interval` is published only when test controls are explicitly enabled and should be disabled during normal use.

Commands and messages are rejected unless they match the configured development boundary:

- Channel ID (the home channel, or a session thread belonging to it)
- User ID

The hub serves only the one configured server, so guild gating is a
deployment property of the hub rather than a per-command check.

## Documentation

Start with:

- [`AGENTS.md`](AGENTS.md) — mandatory instructions for Pi development sessions
- [`docs/product-thesis.md`](docs/product-thesis.md) — purpose, outcome hypotheses, and the practice for preserving why
- [`docs/architecture.md`](docs/architecture.md) — ownership and loop boundaries
- [`docs/project-state.md`](docs/project-state.md) — current known-good state and next milestone
- [`docs/roadmap.md`](docs/roadmap.md) — release plan and longer-term direction
- [`docs/development-workflow.md`](docs/development-workflow.md) — approval and acceptance process
- [`docs/automatic-scheduler.md`](docs/automatic-scheduler.md) — implemented scheduler behavior and guarantees
- [`docs/setup/windows.md`](docs/setup/windows.md) — validated Windows installation procedure
- [`docs/setup/windows-autostart.md`](docs/setup/windows-autostart.md) — validated Windows Task Scheduler autostart
- [`docs/session-handoff.md`](docs/session-handoff.md) — clean new-session prompt template
- [`tests/README.md`](tests/README.md) — black-box testing and test-rationale policy

## Validate

```powershell
pytest
ruff check .
```

## Design direction

Pi provides the model/session runtime through RPC while this application owns the conversation lifecycle, durable state, Discord interaction, and activation timing. Pi launches without filesystem or shell tools, extensions, skills, prompt templates, or project context. The application records persistent session, conversation, and usage metadata in SQLite.
