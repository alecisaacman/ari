# Next Actions for Code Agent (Claude Code / Codex)

Audit date: 2026-06-17

This file is a task queue for a code agent. Each task is self-contained with enough context to execute correctly. Tasks are ordered by priority. Complete earlier tasks before starting later ones.

---

## Priority 1 — Make the Spine Runnable Today

### TASK-001: Write start-ari.sh

**What:** A single shell script that starts the full ARI stack on the home machine.

**Location:** `~/Code/ari/scripts/start-ari.sh`

**Behavior:**
1. Start Postgres via `docker compose up -d postgres`
2. Wait for Postgres to be healthy (poll `pg_isready` up to 10 times, 1s apart)
3. Run `alembic upgrade head`
4. Start `ari-api` with uvicorn on port 8000 (background, log to `logs/ari-api.log`)
5. Start `ari-hub` with uvicorn on port 8001 (background, log to `logs/ari-hub.log`)
6. Print: "ARI stack started. Hub: http://localhost:8001 | API: http://localhost:8000"

**Requirements:** The script must activate the `.venv` before running Python commands. Create `logs/` directory if it doesn't exist. Make the script executable (`chmod +x`).

**Files to check before writing:**
- `~/Code/ari/compose.yaml` — confirm Postgres service name and health check
- `~/Code/ari/pyproject.toml` — confirm entry points for ari-api and ari-hub
- `~/Code/ari/.venv/` — confirm venv exists before writing activation commands

---

### TASK-002: Write stop-ari.sh

**What:** A script that gracefully stops the ARI stack.

**Location:** `~/Code/ari/scripts/stop-ari.sh`

**Behavior:**
1. Kill uvicorn processes running on ports 8000 and 8001 (gracefully via `kill -TERM`, fallback `kill -9`)
2. Run `docker compose stop postgres`
3. Print confirmation

---

### TASK-003: Write daily-check.sh

**What:** A morning ritual script. Run this every morning.

**Location:** `~/Code/ari/scripts/daily-check.sh`

**Behavior:**
1. Print today's date
2. Show current DailyState: `ari state show --today` (or the appropriate CLI command)
3. Trigger an orchestration run for today
4. Show the latest orchestration run output: `ari orchestration latest --state-date [today]`
5. If any CRITICAL alerts exist in the output, print them prominently with a separator

**Requirements:** Activate `.venv` before running `ari` CLI commands. Handle the case where the API is not running (print error and exit cleanly rather than stack trace).

---

### TASK-004: Write a launchd plist for daily orchestration

**What:** A macOS launchd agent that runs the orchestration command automatically every morning.

**Location:** `~/Code/ari/scripts/com.ari.daily-orchestration.plist`

**Behavior:**
- Run daily at 07:00 AM
- Execute: activate venv, then `ari orchestration run --state-date [today]` (or equivalent core trigger)
- Write stdout/stderr to `~/Code/ari/logs/daily-orchestration.log`

**Include in output:**
- The plist file content
- The install command: `cp ~/Code/ari/scripts/com.ari.daily-orchestration.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.ari.daily-orchestration.plist`

**Note:** Check whether `ari orchestration run` is an existing CLI command before writing. If it doesn't exist, note this as a prerequisite.

---

## Priority 2 — Connect Career to ARI Spine

### TASK-005: Write career-to-openloops.py

**What:** A one-time (then recurring) sync script that reads career tracker data and creates OpenLoop records in the ARI Postgres database.

**Location:** `~/Code/ari/scripts/career-to-openloops.py`

**Input sources:**
1. `~/Code/openai-dev-sandbox/data/career_tracker.csv` — career applications
2. `~/Code/openai-dev-sandbox/data/remote_cashflow.sqlite` — opportunity scores (optional, for priority mapping)

**Behavior for each active career application (status not 'rejected' or 'closed'):**
1. Check if an OpenLoop with `source == "career_command_center"` and a matching company+role key already exists
2. If yes: update `last_touched_at` if status changed
3. If no: create a new OpenLoop:
   - `title`: `"Application: {company} — {role}"`
   - `kind`: TASK
   - `priority`: HIGH if top-scored, MEDIUM otherwise
   - `source`: `"career_command_center"`
   - `notes`: current status + any relevant context
   - `opened_at`: application date or today

**Requirements:**
- Uses `ari-memory` repositories and `ari-state` models (do not write raw SQL)
- Must activate the ARI venv and set `PYTHONPATH` correctly (see `pyproject.toml` for the path list)
- Must be idempotent (safe to run multiple times)
- Print a summary at the end: "Created X new loops, updated Y existing, skipped Z already-resolved"

---

### TASK-006: Add macOS notification delivery to alert output

**What:** Add a notification delivery function that sends a macOS system notification for any CRITICAL or INTERRUPTIVE alerts from the latest orchestration run.

**Location:** `~/Code/ari/scripts/notify-alerts.py`

**Behavior:**
1. Connect to Postgres (use ari-memory session)
2. Query alerts from today's latest orchestration run where `escalation_level IN ('interruptive', 'elevated')` and `sent_at IS NULL`
3. For each alert, call:
   ```python
   subprocess.run(["osascript", "-e",
       f'display notification "{alert.message}" with title "ARI: {alert.title}"'])
   ```
4. Mark the alert's `sent_at` field with the current timestamp
5. Print a summary of alerts delivered

**Integration:** Add a call to this script at the end of `daily-check.sh`.

**Requirements:**
- Must use the alert repository from `ari-memory` to update `sent_at` (this requires an API endpoint or direct DB access via the session — check if `PUT /alerts/{id}/mark-sent` exists in ari-api first)
- If the API endpoint doesn't exist, note it as a prerequisite task

---

## Priority 3 — Reduce Structural Debt

### TASK-007: Audit and fix openai-dev-sandbox Python version

**What:** Pin the Python version in `~/Code/openai-dev-sandbox`.

**Steps:**
1. Check which Python version is being used: `python3 --version` in that directory
2. Create `~/Code/openai-dev-sandbox/.python-version` with the detected version (e.g., `3.11`)
3. If a `pyproject.toml` exists without `requires-python`, add `requires-python = ">=3.11"` (or detected version)
4. Report: what version was found, what was created

---

### TASK-008: Audit for a missing .env.example in openai-dev-sandbox

**What:** Confirm whether `~/Code/openai-dev-sandbox/.env.example` exists. If not, create one.

**Check:** Read the existing `.env` file structure (not its values — only the key names). Create `.env.example` with the same keys but placeholder values.

**Example output:**
```
OPENAI_API_KEY=your-openai-api-key-here
```

Do not expose any actual values from `.env`. Only key names.

---

### TASK-009: Write DOMAIN_MODULES.md

**What:** A short architecture document defining the domain module pattern ARI will use as it absorbs external systems.

**Location:** `~/Code/ari/docs/DOMAIN_MODULES.md`

**Content should define:**
1. What a domain module is (an owned area of ARI state that maps to a life domain)
2. The current list of planned domain modules: career, relationships, health, school, self-documentation, finance
3. For each module: what ARI state entities it maps to (OpenLoops, DailyState fields, etc.)
4. The integration pattern: domain module reads from its own storage, writes to canonical ARI state via repositories
5. What modules should NOT own: canonical state, signal logic, alert generation (those stay in the spine)

This doc should be 1–2 pages max. It exists so every future module is built to the same pattern.

---

## Priority 4 — Expand Signal Coverage

### TASK-010: Add stale_open_loop signal to ari-signals

**What:** Add a new signal type that fires when a HIGH or CRITICAL priority open loop has not been touched in more than 7 days.

**Location:** `~/Code/ari/packages/ari-signals/src/ari_signals/engine.py`

**Signal spec:**
- Kind: `"stale_high_priority_loop"`
- Severity: WARNING (one stale loop), CRITICAL (three or more stale loops)
- Summary: `"1 high-priority open loop has been untouched for 7+ days."` (adapt count)
- Reason: explain which loops and how long since last touch
- Evidence: list of stale loop ids, titles, and days-since-touch

**Requirements:**
- Add to `generate_signals()` function alongside the existing three signals
- Write tests in `tests/unit/test_signals.py` covering: no stale loops, one stale HIGH loop, multiple stale loops, a loop that is stale but LOW priority (should not fire)

---

### TASK-011: Add no_daily_check_in signal to ari-signals

**What:** Add a signal that fires when no DailyState has been recorded for today by a configurable time threshold (default: noon).

**Location:** `~/Code/ari/packages/ari-signals/src/ari_signals/engine.py`

**Signal spec:**
- Kind: `"no_daily_check_in"`
- Severity: WARNING
- Summary: `"No daily check-in recorded for today."`
- Reason: Today is [date], detected at [time], and no DailyState exists for this date
- Evidence: the detection timestamp and today's date

**Note:** This signal only makes sense when the orchestration runs on a schedule (after TASK-004). Document this dependency in a comment near the signal function.

**Requirements:**
- The signal should only fire when `detected_at` is after the threshold time (e.g., 12:00 PM in the configured timezone)
- Read timezone from the environment variable `ARI_TIMEZONE` (already in `.env`: `America/Los_Angeles`)
- Write tests covering: no DailyState before noon (signal should NOT fire), no DailyState after noon (signal should fire), DailyState exists (signal should never fire)

---

## Priority 5 — Self-Documentation Foundation

### TASK-012: Write daily log entry on every orchestration run

**What:** Expand `run_signal_orchestration()` to write a structured markdown log file for each run.

**Location of the change:** `~/Code/ari/services/ari-core/src/ari_core/orchestration.py`
**Log output directory:** `~/Code/ari/logs/daily/` (create if not exists)
**Log filename pattern:** `YYYY-MM-DD.md` (append if file exists for today)

**Each entry should include:**
```markdown
## Orchestration Run — [executed_at ISO timestamp]

- State date: [date]
- State fingerprint: [hash]
- Signals detected: [count] — [comma-separated kinds]
- Alerts generated: [count] — [comma-separated titles]
- Open loops: [count active]
- Stress: [value or "not recorded"]
- Priorities: [list]
```

**Requirements:**
- This should be a fire-and-forget write — if the file write fails, log the error but do not raise (do not let logging failure break orchestration)
- The log directory should be gitignored (add `logs/daily/` to `.gitignore`)
- Write a test that confirms the log file is created with the expected fields

---

## Agent Notes

**Before any task:**
1. Read the file you're about to modify
2. Check that imports and dependencies referenced exist in the codebase
3. Verify Python version compatibility (all spine code targets Python 3.12)

**Imports:** The `pyproject.toml` testpaths and pythonpath list the correct source directories. Use those paths when running Python in this repo.

**Do not modify:**
- `.env` files
- Operational SQLite databases (`data/*.sqlite`)
- Existing migration versions
- The canonical state models without explicit instruction

**If a prerequisite is missing (an API endpoint that doesn't exist yet, a CLI command that isn't implemented):**
- Note it clearly
- Either implement the prerequisite first, or implement the current task with a TODO comment marking the integration point
