# One iMessage, traced through ARI

Question: is ARI's logic (open loops, daily state, signals, orchestration) the real
system, or a thin pass-through to the Haiku model? Answer: the real system. The
model reads and writes ARI's records only through ARI's tools. Every decision that
must not be left to a model (control, approval, budget, alerts, reminders) is made
by ARI's code, with no model call. Traced on 2026-11-06 from the code on `main`.

## The trace: "add milk to my list, and what's on my plate?"

| Step | Where | What runs | Model? |
|---|---|---|---|
| 1. Messages.app writes the text to `chat.db` | macOS | | no |
| 2. `/usr/bin/sqlite3` dumps the self-thread every 10 s | launchd job (`launchd.py`) | read-only SQL | no |
| 3. The poller reads the dump, refreshing it if stale | `gateway.py` `_read_dump`, `dump.py` | | no |
| 4. Heartbeat read and written; the poll lock taken | `gateway.py` `poll_once` | | no |
| 5. Echoes of ARI's own replies and tapbacks are dropped | `gateway.py` `_handle`, `_sent_log` | | no |
| 6. If the message waited over 3 min, the gap notice goes first | `gateway.py` `_explain_if_late` | | no |
| 7. Control, pause, spend, budget, review, story, yes/no | `conversation.py` `take` | regex on Alec's words | no |
| 8. Loop breaker and monthly budget checked | `conversation.py`, `brain_usage.py` | | no |
| 9. Haiku answers first with ARI's tools; Sonnet takes over if Haiku calls `use_deeper_model`, or for `think:`/long messages | `brain.py` `respond_to_message`, `_run_turn` | | **yes** |
| 10. Each tool call runs in ARI's code: `create_open_loop` dedupes against open loops (`find_matching_open_loop`), `get_open_loops` merges hub tasks, `get_daily_state` / `get_recent_signals_and_alerts` read the store | `brain.py` `make_tool_dispatcher`, `ari_memory`, `ari_core.state` | typed, validated writes | no |
| 11. Every model request is costed into `brain_usage` | `conversation.py` `_record_call` | | no |
| 12. Reply sent by AppleScript; cursor and conversation saved | `messages_app.py`, `gateway.py` `_save` | | no |
| 13. Signal engine re-runs because a message was handled | `orchestration.py` `run_signal_orchestration`, `ari_signals/engine.py` | five deterministic signals, alerts, decision trail | no |
| 14. Alerts, due reminders, reviews, GET DONE, builds, story | `gateway.py` `_send_*` | quiet hours and pause applied by code | reviews and story only |

## What the model decides, and what it doesn't

- **The model decides:** what the words mean, which ARI tools to call with what
  input, and how to phrase the reply.
- **ARI's code decides:** whether the model is called at all (steps 7 and 8);
  what is stored and how (validated inputs, de-duplicated loops); what counts as a
  signal and when an alert goes out (the engine is pure code over the stored
  state); approvals (from Alec's "yes", never the model); what runs in the
  workspace (the execution gateway); quiet hours, pause, and budget.
- **The model cannot:** approve its own proposal, send a text on its own, raise or
  clear an alert, or see records it didn't fetch through a tool. The system prompt
  forbids answering about Alec's state without checking the tools first.

So the brain is a model on top of ARI, not ARI on top of a model. If the model
disappears (credits out, key rejected, budget used), ARI still pauses, approves,
reports spend, runs signals, and sends alerts and reminders.

## Gaps found

- **Signal timing depends on the poller.** The engine runs only while the poller
  runs. While the Mac sleeps nothing is noticed; that is why the gap notice exists.
- **Dates in some tools use the process clock** (`datetime.now()` in
  `set_daily_state`), not the gateway's injected clock. Harmless live, but it makes
  those tools harder to test at a fixed time.
- **The model can still misread.** A wrong tool input is caught by validation, but
  a well-formed wrong choice (filing a task as a note) is not; the brain eval
  (`evals/brain/run_eval.py`) is the check for that.

## Gap notice (built with this report)

Before, a late reply said only how long ARI was off. Now the same notice, sent once
per gap and written by code from ARI's records, also says what ARI is doing about
it: how many of Alec's messages it is answering in order, and how many reminders
came due while it was off. For example: "Sorry for the slow reply. You sent this at
4:37 AM, and I couldn't see it until now: I wasn't running from 4:10 AM to 4:57 AM,
most likely because your Mac was asleep. Catching up now: answering your 2 messages
in order and sending 1 reminder that came due while I was off."
