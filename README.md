# Socratic Partner

A personal conversational AI designed to challenge assumptions, expose tradeoffs, and help
clarify decisions without optimizing for either validation or disagreement.

## Current status

The project is being built as a sequence of end-to-end increments. The current increment
establishes a guarded Discord development connection and durable local operational state.

Implemented:

- Environment-based configuration
- Explicit guild, channel, and user allowlisting
- Discord application-command registration
- Private `/status`, `/ask-test`, `/pause`, and `/resume` responses
- SQLite schema migration and durable `WAITING`/`PAUSED` state
- Persisted interval and planned next-activation timestamp
- Isolated Pi RPC process with no tools or project resources
- Persistent Pi session metadata and model usage records
- Structured local logs
- Clean Discord client shutdown

Not implemented yet:

- Purpose-driven Socratic conversations (only a fixed connectivity prompt exists)
- Ordinary Discord message handling
- Active scheduling (the next timestamp is stored but not acted upon)
- `/done` or `/interval`
- Discord source ingestion
- Agent prompts or session cards

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
4. Under the installation/OAuth configuration, authorize the `bot` and
   `applications.commands` scopes for your private server.
5. Grant only the permissions currently needed:
   - View Channels
   - Send Messages
   - Read Message History
   - Use Application Commands
6. Do not grant Administrator.

The current increment uses only slash commands, so privileged Message Content Intent is not
required yet. It will be considered when ordinary Discord messages become conversation input.

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
SOCRATIC_PARTNER_DATABASE_PATH=data/socratic_partner.sqlite3
SOCRATIC_PARTNER_DEFAULT_INTERVAL_HOURS=24
SOCRATIC_PARTNER_PI_EXECUTABLE=pi
SOCRATIC_PARTNER_PI_SESSION_DIRECTORY=data/pi-sessions
SOCRATIC_PARTNER_PI_MODEL=
SOCRATIC_PARTNER_PI_TIMEOUT_SECONDS=120
SOCRATIC_PARTNER_LOG_LEVEL=INFO
```

`.env` and runtime data are ignored by Git. Never commit or paste the bot token, client secret,
or other credentials.

## Run

```powershell
socratic-partner
```

When connected, use `/status` in the configured test channel. Use `/ask-test` for a safe,
fixed Pi model call and `/pause` or `/resume` to change durable application state. Responses
are ephemeral and visible only to the invoking user.

Commands are rejected unless all three values match the configured development boundary:

- Guild ID
- Channel ID
- User ID

## Validate

```powershell
pytest
ruff check .
```

## Design direction

Pi will provide the eventual model/session runtime through its RPC mode. This application will
own the conversational workflow, durable state, Discord interaction, and activation timing.
Pi launches without filesystem or shell tools, extensions, skills, prompt templates, or
project context. The application records its persistent Pi session and usage metadata in
SQLite.
