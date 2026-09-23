# Architecture

## Purpose

Socratic Partner helps one user clarify goals, assumptions, tradeoffs, and uncertainty through short Socratic conversations in Discord. It is not a general automation framework.

## Two loops

### Conversation loop

This is application behavior owned by Socratic Partner:

```text
Start conversation
      ↓
Ask one focused question
      ↓
User and model converse
      ↓
User explicitly runs /done
      ↓
Create provisional session card
      ↓
Record the next activation time
```

Socratic Partner owns the prompts, when a conversation is considered open, session-card content, and how user replies are routed.

### Operational activation loop

This is generic timing behavior that may eventually be extracted:

```text
Check durable due time
      ↓
Skip if paused or already active
      ↓
Invoke the application's registered kickoff operation
      ↓
Record generic success or failure
```

The operational loop must not know what a Socratic question means. Socratic Partner should not need to know whether kickoff was requested manually or by a timer.

A small composition layer necessarily knows how to register the application operation with the runtime. The two domain layers do not need mutual knowledge.

## Component ownership

### discord-hub adapter

- Owns no Discord connection and imports no Discord library; discord-hub does.
- Receives allowlisted command invocations and messages through a local HTTP callback.
- Sends ephemeral control responses (via interaction responses/followups) and persistent conversation messages (via the hub API).
- Enforces the channel/user authorization boundary project-side (ADR 0003).
- Creates one session thread per conversation in the configured home channel.
- Does not construct Socratic reasoning itself.

### Socratic application behavior

`SocraticApplication` is the public application-service boundary between interaction adapters
and infrastructure. It:

- Owns prompts and conversation lifecycle.
- Starts a fresh Pi session for each new conversation.
- Coordinates model output, durable state, and a narrow message port.
- Produces a provisional card on `/done`.
- Determines application-specific error behavior.

Discord delegates conversation operations to this service. Tests can use the same public
operations with real temporary SQLite and controlled agent/message ports.

### Pi RPC client

- Owns one isolated Pi subprocess.
- Serializes model runs.
- Persists/resumes Pi session files.
- Rejects assistant messages with `stopReason: error`.
- Runs without tools, extensions, skills, templates, or project context.

### SQLite store

- Owns durable application and conversation metadata.
- Uses explicit schema versions and migrations.
- Stores no secrets.
- Runtime files remain ignored by Git and owned by the deployment.

### Process lifecycle

The automation-harness is embedded as a dependency and owns the process lifecycle: single-instance lock, graceful stop, supervised restart with backoff, structured logs, and `data/status.json`. Windows Task Scheduler (or an equivalent OS facility) starts the process at boot; see [`setup/windows-autostart.md`](setup/windows-autostart.md).

## Session boundaries

Every `/ask-now` or future scheduled activation starts a fresh Pi session. Long-term continuity should later come from selected structured memory—session cards, confirmed observations, open questions, and relevant source records—not one indefinitely growing raw conversation.

## Automation Harness and discord-hub

Automation Harness is embedded as the runtime lifecycle owner (adopted once discord-hub proved the second real need). discord-hub owns the only Discord connection in the ecosystem; Socratic Partner talks to it over a local HTTP API and holds no Discord credentials. Both remain separate projects with their own releases.
