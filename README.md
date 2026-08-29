# Socratic Partner

A personal conversational AI designed to challenge assumptions, expose tradeoffs, and help clarify decisions without optimizing for either validation or disagreement.

## Current status

The v0.09 automatic-scheduler milestone is complete and merged. The project provides persistent Socratic conversations through Discord with optional automatic activation and is currently in the one-week normal-use soak leading toward v0.1.0.

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
- A dedicated Discord application and bot for development

## Install for development

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Configure Automation Lab

In the Discord Developer Portal:

1. Open the **Automation Lab** application.
2. Open **Bot** and create its bot user if it does not already exist.
3. Generate or reset the bot token and keep it secret.
4. Under the installation/OAuth configuration, authorize the `bot` and `applications.commands` scopes for your private server.
5. Grant only the permissions currently needed:
   - View Channels
   - Send Messages
   - Read Message History
   - Use Application Commands
6. Under **Bot → Privileged Gateway Intents**, enable **Message Content Intent**.
7. Do not grant Administrator.

Message Content Intent is required because normal replies in the allowlisted test channel are forwarded into the active Socratic conversation. Messages outside the configured guild, channel, and user boundary are ignored.

Enable Discord Developer Mode to copy your guild (server), test channel, and user IDs.

Copy the configuration template:

```powershell
Copy-Item .env.example .env
```

Fill in `.env` locally:

```dotenv
DISCORD_BOT_TOKEN=your-secret-bot-token
DISCORD_GUILD_ID=your-private-server-id
DISCORD_TEST_CHANNEL_ID=your-private-test-channel-id
DISCORD_ALLOWED_USER_ID=your-user-id
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

`.env` and runtime data are ignored by Git. Never commit or paste the bot token, client secret, or other credentials.

## Run

```powershell
socratic-partner
```

When connected, use `/ask-now` to post the first persistent Socratic question. Reply normally in the configured channel, then use `/done` to generate a provisional session card and close the conversation. Use `/interval` to set 1–720 hours between completed conversations. Control-command responses remain ephemeral; conversation messages and session cards remain visible in the channel. Automatic scheduling is opt-in. `/test-interval` is registered only when test controls are explicitly enabled and should be disabled during normal use.

Commands are rejected unless all three values match the configured development boundary:

- Guild ID
- Channel ID
- User ID

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
- [`docs/session-handoff.md`](docs/session-handoff.md) — clean new-session prompt template
- [`tests/README.md`](tests/README.md) — black-box testing and test-rationale policy

## Validate

```powershell
pytest
ruff check .
```

## Design direction

Pi provides the model/session runtime through RPC while this application owns the conversation lifecycle, durable state, Discord interaction, and activation timing. Pi launches without filesystem or shell tools, extensions, skills, prompt templates, or project context. The application records persistent session, conversation, and usage metadata in SQLite.
