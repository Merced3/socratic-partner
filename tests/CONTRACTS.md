# Test-to-Contract Matrix

This matrix records what evidence exists, its level, and important gaps. “Manual” means a workflow has been exercised through the private Discord deployment but is not reproducible in the default automated suite.

| Product contract | Current evidence | Level | Gap / next evidence |
| --- | --- | --- | --- |
| Unsafe or incomplete configuration fails before connecting | `test_config.py` | Public configuration contract | Add CLI startup test with controlled environment |
| Only the configured guild, channel, and user are accepted | `test_discord_bot.py` | Pure policy unit tests | Discord routing remains manual |
| Provider failures map to provider-independent policies | `test_errors.py` | Pure policy unit tests | Adapter-level failure message path is manual |
| Fresh state is safe and idle | `test_initializes_waiting_state` | Real SQLite integration | None for schema 4 fresh initialization |
| Pause/resume and interval survive process reconstruction | `test_store.py` restart-style tests | Real SQLite integration | Full application restart remains manual |
| Only one conversation can be active | `test_only_one_conversation_can_be_active` | Real SQLite integration | Current raw `sqlite3.IntegrityError` is storage-coupled |
| `/done` stores a card and starts timing from completion | Store lifecycle + `test_complete_conversation_workflow_survives_application_reconstruction` | SQLite integration + application black box | Real Discord/Pi path remains manual |
| Paused completion cannot schedule future work | `test_paused_completion_does_not_schedule_next_question` | Real SQLite integration | None at storage boundary |
| Billing/auth failures pause future activation | `test_errors.py`, `test_billing_error_pauses_automation` | Unit + SQLite integration | Confirmed Discord notification is not automated |
| Pi assistant errors are never accepted as answers | Unit regression + `test_fake_subprocess_rejects_assistant_errors` | Unit + fake-subprocess contract | Real provider error path remains manual |
| Growing Pi sessions do not require full-history retrieval | Command regression + `test_fake_subprocess_honors_jsonl_framing_and_large_events` | White-box regression + fake-subprocess contract | Real growing Pi session remains manual |
| Pi malformed output does not corrupt the next valid exchange | `test_fake_subprocess_recovers_after_malformed_output` | Fake-subprocess contract | Real Pi malformed-output behavior is not induced |
| Pi timeout/reader failure is visible and recoverable | Focused fault tests + `test_fake_subprocess_timeout_resets_and_next_prompt_reuses_client` | White-box fault localization + fake-subprocess contract | Real Pi/provider timeout remains manual |
| `/ask-test` completes through Discord and real Pi | Live acceptance after `e92f724` | Manual black-box | Optional bounded live suite; fake-RPC application test first |
| `/ask-now` behavior posts a question and accepts normal replies | Application workflow test + live Discord acceptance | Automated application black box + manual external path | Thin Discord adapter remains manual |
| Open conversation survives application reconstruction | Application workflow test + live process restart | Automated application black box + manual process test | Real Pi subprocess reconstruction remains manual |
| `/done` behavior posts and stores a provisional session card | Application workflow test + live Discord acceptance | Automated application black box + manual external path | Thin Discord adapter remains manual |
| `/status`, `/interval`, `/pause`, `/resume` Discord behavior | Live Discord acceptance | Manual black-box | Thin adapter/command contract tests |
| Automatic activation occurs only when enabled, waiting, due, idle, and outside backoff | `test_scheduler.py` + controlled rollout | Deterministic policy + manual external path | Forced clean missed-run restart deferred to soak |
| Competing model operations fail fast instead of waiting invisibly | Gate/application/adapter tests + live contention | Unit/application contract + manual external path | None for current single-process policy |
| Automatic active conversation suppresses later due ticks and survives restart | Application/scheduler tests + controlled rollout | Automated application policy + manual process test | Rare Discord-accepted/pre-SQLite crash window accepted |
| Short rollout interval is explicitly gated and durable | Config/command/store tests + live rollout | Automated contracts + manual external path | Test controls disabled during normal use |
| Messages after `/done` do not show a false typing indicator | Adapter regression + live confirmation | Automated thin-adapter regression + manual external path | None for observed defect |
| Channel permission preflight prevents paid undeliverable work | Live regression after Discord 403 | Manual black-box | Controlled Discord adapter test |
| Installed CLI starts and shuts down cleanly | Manual terminal use | Manual black-box | Add subprocess smoke test with injected fake adapters |
| Package metadata is importable | `test_package.py` | Minimal smoke | Does not prove wheel/CLI installation |
| Schema versions 1–3 upgrade to version 4 without data loss | Historical fixtures in `test_store.py` preserve public state; v3 also preserves a completed conversation | Real temporary SQLite migration contract | Add new source-version fixtures before any future migration |
| Start → reply → reconstruct → continue → complete works through public application operations | Application workflow test | Automated application black box | Real Discord/provider/process path remains bounded manual acceptance |

## v0.1.1–v0.5.0 transport and lifecycle update

The v0.5.0 hub migration changed the Discord boundary: discord.py rows above now read as hub-mediated. Discord delivery, reconnect, and identity evidence belongs to discord-hub's own matrix; Socratic Partner evidence now covers the hub contract and project-side policy.

| Product contract | Current evidence | Level | Gap / next evidence |
| --- | --- | --- | --- |
| Pi subprocess never shows a console window | `test_subprocess_creationflags_hide_console_only_on_windows` + live observation | Unit + manual | None for current platform |
| `/model` switches the model in any conversation state | `test_fake_subprocess_switches_model_across_real_pipes` + live `/model` acceptance | Fake-subprocess contract + manual | Autocomplete deferred (hub gap) |
| Each session lives in its own thread; replies outside it are ignored | Authorization policy tests + live acceptance in `#reflection` | Unit + manual black box | Thread delete/archive deferred (hub gap) |
| Discord interaction works without a Discord library or token | Hub client contract tests + live acceptance | Contract + manual black box | Hub downtime delivery is silent-miss (accepted) |
| Authorization gating stays project-side | `test_hub_adapter.py` boundary permutations | Pure policy unit tests | None |
| Harness owns lock, supervision, and prompt stop | Live acceptance: second instance refused, backoff recovery, fast Ctrl+C | Manual black box | None |
| Hub timeouts are reported distinctly from unreachability | `test_slow_hub_reports_timeout_not_unreachable` | Contract | None |
| Textless Pi responses are diagnosable without exposing content | `test_fake_subprocess_empty_text_is_diagnosable` | Fake-subprocess contract | Root cause of the observed instance unknown (transient) |
| `/delete-session` removes local/durable state and requests thread deletion, degrading to manual deletion while the hub lacks the primitive | Store/application/adapter tests (`test_delete_*`, `test_discard_*`) | SQLite integration + application black box + adapter contract | Live Discord acceptance; hub thread-deletion endpoint is an open integration request |
| `/testing` swaps to an isolated data store, refuses mid-conversation, and restores live state untouched | Adapter toggle tests | Adapter contract + real SQLite | Live Discord acceptance; gated behind test controls |

## Remaining bounded evidence

Automatic scheduling has completed controlled rollout. Remaining evidence should not delay the soak unnecessarily:

1. Confirm the post-`/done` typing-indicator regression manually.
2. Keep real Discord/provider testing opt-in and bounded; do not make CI depend on secrets, network availability, or model credits.
3. Treat naturally occurring downtime during the soak as additional missed-run evidence rather than manufacturing more paid tests.

Update this matrix whenever evidence changes. Do not upgrade “manual” to “automated” merely because a lower-level mock passed.
