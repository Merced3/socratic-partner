# Windows Setup

This guide walks through a clean Windows installation of **Socratic Partner** ("Socrates") from an empty development machine to a working Discord-connected process.

It is written for someone who has **none of the required development tools installed yet**.

> **Validated on Windows:** August 27, 2026  
> The exact versions used during the successful setup were Git `2.55.0.windows.3`, Python `3.13.15`, Node.js `24.19.0`, npm `10.9.0`, and Pi `0.84.3`.
>
> Newer versions may work, but if a future version introduces an incompatibility, these versions are a known-good reference point.

---

## What gets installed

Socratic Partner is a Python application, but it also launches **Pi** as a separate AI/model runtime.

The dependency chain is:

```text
Windows
  ├─ Git
  ├─ Python 3.11+
  │   └─ Socratic Partner virtual environment
  │       ├─ discord.py
  │       ├─ python-dotenv
  │       ├─ pytest
  │       └─ ruff
  ├─ Node.js + npm
  │   └─ Pi
  │       └─ AI provider authentication
  └─ Discord
      └─ Bot/application credentials in Socratic Partner's local .env
```

There are **two separate credential layers**:

1. **Pi/provider credentials** — configured through Pi, for example an OpenRouter API key.
2. **Socratic Partner/Discord credentials** — stored locally in the repository's `.env`.

Do not put your AI provider API key into Socratic Partner's `.env` unless a future version of the project explicitly requires that.

---

## 1. Open Windows PowerShell

The first system-level installations can be run from any directory.

For example:

```powershell
PS C:\Users\your-user>
```

Your current folder does not matter yet.

---

## 2. Install Git, Python, and Node.js

Run:

```powershell
winget install --id Git.Git -e --source winget
winget install --id Python.Python.3.13 -e --source winget
winget install --id OpenJS.NodeJS.LTS -e --source winget
```

Windows may show administrator/UAC prompts during installation.

After all three finish, **close PowerShell completely and open a new PowerShell window**. This ensures the newly installed programs and PATH changes are available to the shell.

Verify the installations:

```powershell
git --version
py -3.13 --version
node --version
npm --version
```

A known-good setup produced:

```text
git version 2.55.0.windows.3
Python 3.13.15
v24.19.0
10.9.0
```

The project itself requires Python **3.11 or newer**. Python 3.13 is the currently tested Windows setup.

---

## 3. Install Pi

Socratic Partner does not call an AI provider directly. It launches **Pi** in RPC mode and lets Pi own model sessions and model calls.

Install Pi globally through npm:

```powershell
npm install -g --ignore-scripts @earendil-works/pi-coding-agent@0.84.3
```

Verify it:

```powershell
pi --version
```

Expected for the validated setup:

```text
0.84.3
```

## Updating Pi

If Pi reports that a newer version is available, it can update itself with:

```powershell
pi update
```

For maximum reproducibility, it is reasonable to stay on the version known to work with the project until you intentionally test a newer release.

---

## 4. Choose where the repository will live

The repository can live anywhere you normally keep development projects.

For example:

```text
Documents
└─ Coding
   └─ Automations
      └─ socratic-partner
```

A PowerShell-friendly path is:

```powershell
$HOME\Documents\Coding\Automations
```

Create the parent directory if it does not already exist:

```powershell
New-Item -ItemType Directory -Force "$HOME\Documents\Coding\Automations" | Out-Null
```

Move into it:

```powershell
cd "$HOME\Documents\Coding\Automations"
```

Confirm:

```powershell
Get-Location
```

---

## 5. Clone Socratic Partner

Clone the repository:

```powershell
git clone https://github.com/Merced3/socratic-partner.git
```

Enter it:

```powershell
cd socratic-partner
```

Verify Git state:

```powershell
git status
git log -1 --oneline
```

You should be on `main`, up to date with `origin/main`, with a clean working tree.

At the time this guide was validated, the latest merge commit was:

```text
91fa20d Merge automatic scheduler v0.09 milestone
```

Do not treat that commit as permanently current; it is only a reference for this validated setup.

---

## 6. Create the Python virtual environment

From the repository root:

```powershell
py -3.13 -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

The prompt should now begin with:

```text
(.venv)
```

For example:

```text
(.venv) PS C:\...\socratic-partner>
```

## If PowerShell blocks activation

If PowerShell reports that script execution is disabled, use a process-local policy change:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

This changes the policy only for the current PowerShell process.

---

## 7. Install Socratic Partner and development dependencies

With `.venv` active:

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The editable install includes Socratic Partner itself plus development tools such as `pytest` and `ruff`.

Verify that the executable is available:

```powershell
Get-Command socratic-partner
```

The path should point inside the repository's virtual environment, similar to:

```text
...\socratic-partner\.venv\Scripts\socratic-partner.exe
```

---

## 8. Validate the installation before adding credentials

Still inside the activated virtual environment, run:

```powershell
pytest
ruff check .
```

At the time this guide was validated, the expected result was:

```text
92 passed
```

and:

```text
All checks passed!
```

If the automated checks fail, fix that before adding secrets or trying to connect Discord.

---

## 9. Create the local Socratic Partner configuration

Copy the repository's template:

```powershell
Copy-Item .env.example .env
```

Open it locally:

```powershell
notepad .env
```

Never commit `.env`.

Never paste its full contents into an issue, chat, terminal transcript, screenshot, or public log.

Do not run commands such as the following if their output might be shared:

```powershell
Get-Content .env
cat .env
```

The repository is configured to ignore `.env`, but you should still treat it as secret material.

---

## 10. Configure the Discord application

Socratic Partner currently expects a private Discord development boundary consisting of:

- one Discord server/guild,
- one allowed channel,
- one allowed user,
- one dedicated Discord bot/application.

In the Discord Developer Portal:

1. Create or open the Discord application used for Socratic Partner.
2. Create its bot user if necessary.
3. Generate or reset the bot token.
4. Keep the token secret.
5. Authorize the bot to the private server with:
   - `bot`
   - `applications.commands`
6. Grant only the permissions currently needed:
   - View Channels
   - Send Messages
   - Read Message History
   - Use Application Commands
7. Under **Bot → Privileged Gateway Intents**, enable **Message Content Intent**.
8. Do **not** grant Administrator unless a future version explicitly requires it.

Message Content Intent matters because ordinary replies in the allowlisted channel are forwarded into the active Socratic conversation.

Enable Discord Developer Mode so you can copy:

- Guild/server ID
- Channel ID
- Your personal Discord user ID

The allowed user ID should be your **human user account ID**, not the bot/application ID.

---

## 11. Fill in `.env`

At minimum, fill in the Discord-specific values:

```dotenv
DISCORD_BOT_TOKEN=your-secret-bot-token
DISCORD_GUILD_ID=your-private-server-id
DISCORD_TEST_CHANNEL_ID=your-private-test-channel-id
DISCORD_ALLOWED_USER_ID=your-user-id
```

The current configuration template also includes:

```dotenv
SOCRATIC_PARTNER_TEST_MODE=true
SOCRATIC_PARTNER_TEST_CONTROLS_ENABLED=false

SOCRATIC_PARTNER_DATABASE_PATH=data/socratic_partner.sqlite3
SOCRATIC_PARTNER_DEFAULT_INTERVAL_HOURS=24

SOCRATIC_PARTNER_AUTOMATIC_SCHEDULER_ENABLED=false

SOCRATIC_PARTNER_PI_EXECUTABLE=pi
SOCRATIC_PARTNER_PI_SESSION_DIRECTORY=data/pi-sessions
SOCRATIC_PARTNER_PI_MODEL=
SOCRATIC_PARTNER_PI_TIMEOUT_SECONDS=120

SOCRATIC_PARTNER_LOG_LEVEL=INFO
```

## Recommended first-run behavior

For the first launch, keep:

```dotenv
SOCRATIC_PARTNER_TEST_MODE=true
SOCRATIC_PARTNER_TEST_CONTROLS_ENABLED=false
SOCRATIC_PARTNER_AUTOMATIC_SCHEDULER_ENABLED=false
```

This keeps automatic scheduling off while you verify the manual conversation loop.

Once the application has been validated, automatic scheduling can be intentionally enabled:

```dotenv
SOCRATIC_PARTNER_AUTOMATIC_SCHEDULER_ENABLED=true
```

Restart the process after changing `.env`.

---

## 12. Configure Pi's AI provider

Pi must have access to at least one model before Socratic Partner can use it.

This is configured **in Pi**, separately from Socratic Partner's `.env`.

It is usually cleaner to leave the Socratic Partner repository before performing interactive Pi setup:

```powershell
deactivate
cd $HOME
pi
```

If Pi starts with:

```text
Warning: No models available.
```

that means Pi is installed correctly but no provider has been authenticated yet.

## OpenRouter example

OpenRouter is a practical starting point because one account can expose models from many providers.

The exact OpenRouter website layout may change over time, but the general process is:

1. Create or sign in to an OpenRouter account.
2. Open the API Keys section.
3. Create a new API key.
4. Give it a recognizable name.
5. Copy the key.
6. Store it securely.
7. Do not share it or commit it.

Back in Pi:

```powershell
pi
```

Then enter:

```text
/login
```

Choose:

```text
Sign in with an API key
```

Select or search for:

```text
openrouter
```

Paste the private OpenRouter API key into Pi's credential field and submit it.

The API key should remain in Pi's authentication storage. It should **not** be copied into Socratic Partner's `.env`.

---

## 13. Select and test a Pi model

Inside Pi:

```text
/model
```

Choose a model.

A model used successfully during this Windows setup was:

```text
openrouter/openai/gpt-5.4-mini
```

Model catalogs, pricing, capabilities, and names change over time, so confirm the current provider information before relying on any particular model.

A very small test prompt is enough to prove that authentication works.

For example:

```text
This is a connection test. Reply with only: Test received.
```

Once Pi successfully responds, provider authentication is working.

Exit Pi when finished.

---

## 14. Choose the model Socratic Partner should use

Return to the repository:

```powershell
cd "$HOME\Documents\Coding\Automations\socratic-partner"
```

If you want Socratic Partner to request a specific Pi model, set it in `.env`:

```dotenv
SOCRATIC_PARTNER_PI_MODEL=openrouter/openai/gpt-5.4-mini
```

If this value is left blank:

```dotenv
SOCRATIC_PARTNER_PI_MODEL=
```

Socratic Partner lets Pi use its configured default model.

Using an explicit model is more predictable. Leaving it blank makes changing Pi's default model easier.

Remember:

- **Model identifier:** may be stored in `.env`.
- **Provider API key:** authenticate through Pi; do not place it in this `.env`.

---

## 15. Launch Socratic Partner

Every new PowerShell session must reactivate the repository's virtual environment before the `socratic-partner` command will be available.

From the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then launch:

```powershell
socratic-partner
```

A successful startup should produce logs similar to:

```text
INFO discord.client: logging in using static token
INFO socratic_partner.discord_bot: Synchronized ... command(s) to the development guild.
INFO discord.gateway: ... connected to Gateway ...
INFO socratic_partner.discord_bot: Connected to Discord as ...
```

At this point Socratic Partner is connected to Discord.

---

## 16. Harmless voice-support warnings

You may see warnings similar to:

```text
WARNING discord.client: PyNaCl is not installed, voice will NOT be supported
WARNING discord.client: davey is not installed, voice will NOT be supported
```

These warnings do **not** mean Socratic Partner failed to start.

The current application does not require Discord voice support. If the process continues and reports that it connected to Discord, these warnings can be ignored.

Do not install extra voice dependencies unless the project later adds a real voice feature that needs them.

---

## 17. Perform a Discord smoke test

With Socratic Partner running, use the configured Discord server and channel.

A useful first validation sequence is:

1. Run `/status`.
2. Run `/ask-now`.
3. Confirm that Socratic Partner posts an opening question.
4. Reply normally in the configured channel.
5. Confirm that the conversation continues.
6. Run `/done`.
7. Confirm that the session closes and a provisional session card is created.

The exact available commands depend on the repository version and feature flags.

At the time this guide was validated, the normal command set included:

- `/status`
- `/ask-test`
- `/ask-now`
- `/done`
- `/interval`
- `/pause`
- `/resume`

Short-interval test controls are intentionally hidden unless explicitly enabled.

---

## 18. Normal startup after the machine has already been configured

After the one-time setup is complete, you do **not** need to reinstall anything each time.

For a new PowerShell session:

```powershell
cd "$HOME\Documents\Coding\Automations\socratic-partner"
.\.venv\Scripts\Activate.ps1
socratic-partner
```

That is the normal manual startup sequence.

To stop the process, use:

```text
Ctrl+C
```

---

## 19. Common problems

## `socratic-partner` is not recognized

Example:

```text
socratic-partner : The term 'socratic-partner' is not recognized...
```

Most likely cause: the Python virtual environment is not active.

From the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then:

```powershell
Get-Command socratic-partner
socratic-partner
```

The executable was installed inside `.venv`, not globally on Windows.

---

## `pi` is not recognized

First close and reopen PowerShell after installing Node.js/npm or Pi.

Then check:

```powershell
Get-Command pi
pi --version
```

If necessary, reinstall Pi:

```powershell
npm install -g --ignore-scripts @earendil-works/pi-coding-agent@0.84.3
```

---

## Pi says `No models available`

Pi has not been authenticated with a provider.

Start Pi:

```powershell
pi
```

Then:

```text
/login
```

Authenticate with the provider you intend to use.

---

## Pi works interactively but Socratic Partner cannot start Pi

Make sure `pi` is available from the same Windows environment:

```powershell
Get-Command pi
```

The `.env` should normally contain:

```dotenv
SOCRATIC_PARTNER_PI_EXECUTABLE=pi
```

Socratic Partner searches for that executable on PATH.

---

## Discord commands do not appear

Check that:

- the bot was installed in the correct Discord server,
- `applications.commands` was included when installing it,
- `DISCORD_GUILD_ID` is correct,
- the bot successfully logs in,
- startup logs say commands were synchronized.

---

## Slash commands work, but ordinary replies are ignored

Check:

- **Message Content Intent** is enabled in the Discord Developer Portal,
- `DISCORD_TEST_CHANNEL_ID` matches the channel being used,
- `DISCORD_ALLOWED_USER_ID` is your human user ID,
- `DISCORD_GUILD_ID` is correct.

Socratic Partner deliberately ignores messages outside its configured guild/channel/user boundary.

---

## Discord login/authentication fails

The bot token may be invalid, expired, reset, or copied incorrectly.

Generate/reset the token in the Discord Developer Portal and update only:

```dotenv
DISCORD_BOT_TOKEN=...
```

Do not print the token while troubleshooting.

---

## Provider returns billing or rate-limit errors

A working Pi installation does not guarantee that the selected provider has available credit or capacity.

Examples include:

- billing/credit errors,
- authentication errors,
- HTTP 402-class failures,
- HTTP 429 rate limits,
- provider availability failures.

Check the provider's billing, credits, model availability, and rate limits.

Socratic Partner contains provider-independent handling for several model-runtime failure classes, but the provider itself still needs to be healthy and funded.

---

## Cloudflare AI Gateway

Pi can be used with providers other than OpenRouter, and Cloudflare AI Gateway may be attractive for more centralized or production-oriented routing.

It is **not required** for Socratic Partner.

This Windows guide uses OpenRouter as the concrete example because it is straightforward to authenticate and gives access to a broad model catalog.

If you switch to Cloudflare AI Gateway or another provider, validate billing behavior, rate limits, long-running reliability, model identifiers, and Pi compatibility before depending on it.

---

## 20. Security checklist

Before considering the installation complete:

- `.env` exists only locally.
- `.env` has not been committed.
- Discord bot token has not been shared.
- AI provider API keys have not been committed.
- Provider authentication was performed through Pi.
- Runtime SQLite databases are not committed.
- Pi session files are not committed.
- Logs containing sensitive runtime data are not committed.
- The Discord bot does not have Administrator permission.
- Guild/channel/user allowlisting matches the intended private deployment.

You can verify Git is clean without printing `.env`:

```powershell
git status
```

---

## 21. Final validation checklist

A complete Windows setup should satisfy all of the following:

```text
Git installed
Python 3.11+ installed
Node.js/npm installed
Pi installed
Repository cloned
Python .venv created
.venv activated
Socratic Partner installed in editable mode
pytest passes
ruff check . passes
.env created locally
Discord credentials configured
Discord Message Content Intent enabled
Pi provider authenticated
Pi can successfully call a model
SOCRATIC_PARTNER_PI_MODEL configured or intentionally left blank
socratic-partner executable is visible while .venv is active
Socratic Partner connects to Discord
Manual Discord conversation smoke test succeeds
```

Once all of those are true, the Windows installation is operational.

---

## Notes on Pi and provider choice

Socratic Partner intentionally keeps its model runtime outside the application itself.

Pi owns:

- provider authentication,
- model selection/runtime,
- model sessions,
- model calls,
- compaction/tool-loop behavior where applicable.

Socratic Partner owns:

- Discord interaction,
- Socratic conversation behavior,
- application lifecycle,
- persistent application state,
- activation timing.

That separation is important. It means a provider can be changed without redesigning the Socratic Partner application.

OpenRouter is only the example in this guide, not a requirement.

When choosing a provider/model, consider:

- cost,
- rate limits,
- context limits,
- reliability,
- latency,
- model quality,
- reasoning settings,
- whether long-running sessions behave predictably.

Large models and high reasoning settings can become expensive quickly. Validate the workflow with inexpensive test prompts before leaving long-running or automatic behavior enabled.
