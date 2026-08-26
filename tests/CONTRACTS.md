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
| `/done` stores a card and starts timing from completion | `test_conversation_lifecycle_sets_next_interval` | Real SQLite integration | Discord/Pi workflow remains manual |
| Paused completion cannot schedule future work | `test_paused_completion_does_not_schedule_next_question` | Real SQLite integration | None at storage boundary |
| Billing/auth failures pause future activation | `test_errors.py`, `test_billing_error_pauses_automation` | Unit + SQLite integration | Confirmed Discord notification is not automated |
| Pi assistant errors are never accepted as answers | `test_rejects_settled_assistant_error` | White-box protocol regression | Replace/supplement with fake RPC subprocess contract |
| Growing Pi sessions do not require full-history retrieval | `test_prompt_does_not_request_complete_message_history` | White-box regression | Add fake RPC subprocess and oversized-event scenario |
| Pi timeout/reader failure is visible and recoverable | `test_settle_timeout_resets_process`, `test_reader_failure_event_is_reported` | White-box fault injection + manual acceptance | Automate successful next operation after reset |
| `/ask-test` completes through Discord and real Pi | Live acceptance after `e92f724` | Manual black-box | Optional bounded live suite; fake-RPC application test first |
| `/ask-now` posts a question and accepts normal replies | Live Discord acceptance | Manual black-box | Extract application service and automate with recording message port |
| Open conversation survives process restart | Live Discord acceptance + store tests | Manual black-box + integration | Automate complete application reconstruction |
| `/done` posts a provisional session card | Live Discord acceptance + store lifecycle | Manual black-box + integration | Automate through application service |
| `/status`, `/interval`, `/pause`, `/resume` Discord behavior | Live Discord acceptance | Manual black-box | Thin adapter/command contract tests |
| Channel permission preflight prevents paid undeliverable work | Live regression after Discord 403 | Manual black-box | Controlled Discord adapter test |
| Installed CLI starts and shuts down cleanly | Manual terminal use | Manual black-box | Add subprocess smoke test with injected fake adapters |
| Package metadata is importable | `test_package.py` | Minimal smoke | Does not prove wheel/CLI installation |
| Schema versions 1–3 upgrade to version 4 without data loss | None | Missing | Add fixture-based migration tests before another migration |
| Full manual conversation loop works end to end | Live acceptance | Manual black-box | Highest-priority automated scenario before v0.09 |

## Priority gaps before automatic scheduling

1. Introduce a small application-service boundary without changing behavior.
2. Automate start → reply → reconstruct → continue → `/done` using real temporary SQLite, a fake model runtime, and a recording message port.
3. Add schema 1→4, 2→4, and 3→4 preservation tests.
4. Add a fake Pi RPC subprocess contract test, including a large event and timeout recovery.
5. Keep real Discord/provider testing opt-in and bounded; do not make CI depend on secrets, network availability, or model credits.

Update this matrix whenever evidence changes. Do not upgrade “manual” to “automated” merely because a lower-level mock passed.
