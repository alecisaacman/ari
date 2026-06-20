# ARI/ACE Implementation Roadmap

Audit date: 2026-06-17

---

## Governing Principles for This Roadmap

1. **Feed the brain before expanding it.** ARI cannot surface patterns it has never observed. Daily use must come first.
2. **One domain at a time.** Absorb career, then relationships, then health. Do not try to model everything at once.
3. **Integration before features.** Connect the career system to ARI before building new career features.
4. **Real proactivity before smart proactivity.** A dumb notification that always fires is more valuable than a smart one that never fires.
5. **The self-documentation module grows with everything else.** Every real capability should feed the record.

---

## TODAY — Make ARI Real for the First Time

These actions require no code changes. They are about beginning to operate the system you have.

**1. Start the ARI stack and confirm it runs**
```bash
cd ~/Code/ari
docker compose up -d postgres
alembic upgrade head
uvicorn ari_api.main:app --port 8000 &
uvicorn ari_hub.main:app --port 8001 &
```
Open `http://localhost:8001`. Confirm the hub loads.

**2. Enter today's DailyState via the hub form**
- Top 3 priorities (what matters today, right now)
- Win condition (what does a good day look like)
- Movement (yes/no)
- Stress level (1–10)
- Next action

**3. Enter this week's WeeklyState**
- 3 outcomes you're working toward this week
- Cannot-drift commitments (what you will not let slip)
- Current blockers

**4. Enter your top 5–10 current open loops**
Any active commitment, pending decision, or unresolved thread. Job applications, school deadlines, personal commitments, things you said you'd do. Get them into the system.

**5. Trigger an orchestration run**
```bash
ari orchestration latest --state-date $(date +%Y-%m-%d)
```
ARI will now generate its first real signals about your life.

**Why today:** You cannot evaluate what ARI needs next until you see what it actually surfaces with real data. Today's check-in is the baseline.

---

## 1-DAY — Make It Easy to Use Daily

**1. Write a single startup script (`start-ari.sh`)**

One command starts Postgres, ari-api, and ari-hub. No more remembering the sequence.

```bash
#!/bin/bash
cd ~/Code/ari
docker compose up -d postgres
sleep 2
uvicorn ari_api.main:app --port 8000 --daemon
uvicorn ari_hub.main:app --port 8001 --daemon
open http://localhost:8001
```

Consider adding this to a macOS login item or launchd agent.

**2. Write a daily check-in script (`daily-check.sh`)**

A simple CLI ritual for the morning:

```bash
#!/bin/bash
echo "=== ARI Morning Check-In ==="
date
ari state show --today
ari orchestration latest --state-date $(date +%Y-%m-%d)
```

Run this every morning. Open the hub if signals are present.

**3. Add a launchd plist for automatic daily orchestration**

Create `~/Library/LaunchAgents/com.ari.daily-orchestration.plist` to run the orchestration script every morning at 7am. This is the first step toward genuine proactivity — ARI will generate signals every day whether or not you open the hub.

**4. Add `.python-version` to openai-dev-sandbox**

Pin the Python version so the career system and ARI spine are on the same interpreter when absorbed.

---

## 1-WEEK — Connect Career to ARI

The career system has the most live data. It should be the first domain absorbed into the spine.

**1. Write a career → OpenLoop sync script**

Read current career tracker status from `data/career_tracker.csv` or `remote_cashflow.sqlite`. For each active application, create an `OpenLoop` record in Postgres:
- `title`: "Application: [Company] — [Role]"
- `kind`: TASK
- `priority`: based on career scoring
- `source`: "career_command_center"
- `notes`: application status, packet link

This is ~50 lines of Python and it immediately populates ARI with real, structured open loops from your most active domain.

**2. Map career daily actions to DailyState priorities**

When `career_command_center` generates daily actions, write the top 3 into `DailyState.priorities` for today. This makes ARI's daily state reflect actual current work instead of being manually maintained separately.

**3. Wire one notification path**

Pick the simplest possible notification delivery:

**Option A: macOS notification (simplest)**
```python
import subprocess
subprocess.run(["osascript", "-e", f'display notification "{alert.message}" with title "ARI"'])
```

**Option B: Terminal print at shell startup**
Add to `.zshrc`:
```bash
python3 ~/Code/ari/scripts/ari-morning-brief.py
```
Print pending alerts when a new terminal session opens.

Either option. Just pick one and ship it. ARI will start proactively reaching you.

**4. Consolidate the three Streamlit dashboards**

Create one `ari_dashboard.py` that combines the useful panels from all three. Archive the originals.

**5. Fix the `apps/ace_command_center` naming**

Rename or symlink the frontend directory so it's clearly paired with its backend:
```
apps/ace-command-center/
    backend/   (currently apps/ace_command_center/backend/)
    frontend/  (currently apps/ace-command-center/frontend/)
```

---

## 30-DAY — Domain Expansion and Real Proactivity

By this point ARI should be running daily, generating real signals, and delivering notifications.

**Domain: Relationships (networking-crm → ARI)**

1. Formalize `modules/networking-crm` as an ARI domain module in `~/Code/ari/modules/`
2. Create a Postgres-backed `Contact` and `NetworkingAction` model
3. Map unanswered contacts and overdue follow-ups to `OpenLoop` records
4. Add a `contact_follow_up_stale` signal to `ari-signals`

**Domain: Health (minimal baseline)**

Expand beyond the current stress + movement fields:
1. Add sleep quality (1–10) to DailyState
2. Add physical_state notes field
3. Add a 7-day moving average stress signal: `chronic_stress_pattern`
4. Make movement tracking more specific (type of exercise, duration)

These are data model changes (new migration) + signal additions. Keep it simple.

**Proactive: Expand the signal engine**

Current signals: 3 (open_loop_accumulation, weekly_trajectory_drift, elevated_stress)

Add:
- `stale_open_loop`: any open loop untouched for >7 days at HIGH priority
- `no_daily_check_in`: no DailyState recorded for the current day by noon
- `career_application_velocity_low`: fewer than N applications in the past 7 days
- `week_nearing_end_no_reflection`: Friday afternoon, no weekly lesson recorded

Each of these requires a new signal function in `ari-signals/engine.py` + a migration if new state fields are needed.

**Executor: Add one real action**

Expand the executor beyond pytest. First candidate:
- `WRITE_FILE`: write a daily log entry to `~/Code/ari/logs/YYYY-MM-DD.md`

This makes ARI's governed execution actually do something visible. Every day ARI runs, it creates a dated log file summarizing its orchestration run. This is the foundation of the self-documentation module.

**Self-documentation: Formalize the module**

Create `~/Code/ari/modules/self-doc/` (or as a service):
1. On every orchestration run, write a structured log entry
2. Include: date, signals detected, alerts generated, state fingerprint, open loop count
3. Add a weekly summary generator that compiles the week's log entries into a markdown narrative
4. These summaries feed the "ARI series" content you want to post

The `networking-crm` project's `clip.py`, `frame.py`, `storyboard.py`, `video.py` pipeline belongs here eventually — a way to produce visual records of ARI's activity.

---

## 90-DAY — Toward Full Operating System

By 90 days, ARI should be the central operating surface for at least 4 domains.

**LLM Integration**

The spine currently has zero LLM calls. This is intentional — build the data model first. At 90 days, the first LLM integration should be:
- **Natural language state entry**: Instead of form fields, tell ARI what you did today in plain text. ARI extracts DailyState fields.
- **Weekly summary generation**: ARI reads the week's state and writes a narrative summary.
- **Signal explanation**: ARI can explain, in natural language, why a signal was generated.

Do not add LLM calls to the orchestration or execution path until you trust the deterministic signal engine. Trust is built from months of real use, not from architecture.

**Domain: School**

When school is active, add:
- `Assignment` model with due dates and course context
- Assignments flow to `OpenLoop` with project linkage
- Add `deadline_approaching` signal

**Voice Input**

Only after: LLM integration is working, daily use is established, the state model is stable.

Voice input is an input surface, not a core system. It should call the same API as the hub and CLI. Do not build a separate voice pipeline.

---

## What NOT to Do

| Don't | Why |
|---|---|
| Add more Streamlit dashboards | You have three. They're all read-only. Consolidate. |
| Expand the controller/authority framework | The executor can only run pytest. More governance rules on nothing is maintenance work with no benefit. |
| Build mobile/phone surfaces | Build the daily desktop ritual first. Phone is a reduced-interface version of something that doesn't fully exist yet. |
| Add more agent types to the Agent Hub | 22 agents are already registered. None of them have real execution wired. Adding more catalog entries is not progress. |
| Move off Postgres to SQLite for the spine | Postgres enables the long-term intelligence features (full-text search, time-series queries, proper indexing). SQLite's simplicity is not worth losing these capabilities. |
| Build a new frontend framework for the hub | The server-rendered HTML hub is clean, fast, and maintainable. Add CSS before adding React. |
| Start using ARI before entering real data | An empty ARI that you "check in on" is theater. Real data first. |

---

## Milestone Checkpoints

| Milestone | Success Criterion |
|---|---|
| M1: Spine is live | ARI hub is open, shows real DailyState and OpenLoops, generates at least 1 real signal |
| M2: Daily habit | 7 consecutive days of DailyState entries in Postgres |
| M3: Career connected | Career applications are OpenLoop records in ARI, daily career actions appear in priorities |
| M4: Proactive | At least 1 alert delivered as a notification outside the hub |
| M5: Multi-domain | Career + relationships + health all tracked as ARI state, 3+ signal types active |
| M6: Self-documenting | Every orchestration run produces a dated log entry, weekly summaries exist |
| M7: Executing | Executor performs at least 1 real-world action (write log, send notification) via the governed cycle |
