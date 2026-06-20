# ARI/ACE Product Strategy Audit

Audit date: 2026-06-17

---

## The Vision (as stated)

ARI/ACE should become a serious personal AI operating system that helps you think, plan, execute, track, and improve across life, work, school, health, career, relationships, and projects.

More specifically:
- **One persistent intelligence** that understands you across all life domains
- **Proactive** — ARI notices things, surfaces them, and acts without being asked
- **Cross-domain** — career, health, relationships, school, personal projects, all tracked in one place
- **Executes automations** — ARI takes real actions when it deems them appropriate
- **Self-documenting** — ARI maintains a living record of itself, its activity, and can produce shareable content about that record
- **Multi-surface** — terminal, browser hub, phone, voice — all windows into the same brain

This is the JARVIS model: one intelligence, ambient presence, quiet until something matters, immediately serious when stakes rise.

---

## What Currently Exists vs. The Vision

### Exists: A well-architected brain that has never been fed

The ARI spine has the right data model, the right persistence design, and the right explainability philosophy. The state schema (DailyState, WeeklyState, OpenLoops, Signals, Alerts) is exactly correct for a personal OS foundation.

The problem: the brain has no data. You have not been using it daily. You cannot build a proactive intelligence on an empty database.

### Exists: A career automation system that is actually running

The ACE Command Center career tools are real. They have scraped jobs, scored opportunities, generated application packets, and created daily action queues. There is live data in SQLite databases. This is the most operationally complete part of the system.

The problem: it is completely disconnected from ARI. Career priorities, job applications, and daily career actions do not flow into ARI's state model. ARI cannot see them.

### Exists: Early prototypes of self-documentation

The `~/ARI(codex)` folder contains early captures from April 2026: screen clips, framed terminals, live priority demos, storyboards. This is the beginning of ARI's self-documentation capability — capturing its own activity as it happens and building a visual/text record.

The `networking-crm` project goes further: it has `clip.py`, `frame.py`, `storyboard.py`, `video.py`, and `content.py` — a content pipeline for producing formatted output from ARI sessions. `ari.py` suggests integration hooks back to the main system were intended.

The problem: these prototypes are not connected to the spine and not running automatically.

### Missing: The proactive loop

The most important missing piece is a continuous feedback loop:

1. ARI ingests state from all domains (career actions, calendar, health, open loops)
2. ARI detects signals from that state
3. ARI surfaces relevant information proactively (notification, hub update)
4. ARI executes small automations when confidence is high
5. ARI logs everything (building the self-documentation record)
6. Loop continues on a schedule, not on demand

Currently, step 1 requires manual entry, step 3 never happens (alerts aren't delivered), step 4 is limited to running tests, and step 6 is partial (orchestration runs are logged but not surfaced).

---

## Domain Coverage Assessment

| Domain | ARI State Fields | Real Data | Connected | Notes |
|---|---|---|---|---|
| Career | OpenLoop (indirect) | In ACE/SQLite | No | Rich data in openai-dev-sandbox, totally disconnected |
| Work / Daily Execution | DailyState (priorities, win condition, next action) | None | N/A | Schema exists, nothing written |
| Weekly Planning | WeeklyState (outcomes, cannot_drift, blockers) | None | N/A | Schema exists, nothing written |
| Health | DailyState.stress (1–10), DailyState.movement (bool) | None | N/A | Extremely limited |
| Relationships | None | In networking-crm | No | networking-crm exists but isolated |
| School | None | None | N/A | Not modeled at all |
| Projects | Project model exists | None | N/A | Model exists, nothing written |
| Self-documentation | None in spine | Clips/frames in ~/ARI | No | Prototype exists, not integrated |
| Finance | Agent registered in hub | None | No | Agent catalog only |

The current system only covers 2 of 8 intended domains, and even those have no real data in them.

---

## What Is Overbuilt

### 1. The Controller/Authority/Execution Governance Framework

The spine has a sophisticated autonomous execution safety system:
- Rule-based authority evaluation (confidence thresholds, approval gates, action-count limits)
- ControllerDecision → ActionPlan → WorkerRun → VerificationResult trajectory
- Ordered ControllerEvent stream for replay
- PendingApproval workflow with approve/deny/resume

This is the right architecture for an AI agent that takes real actions in the world. It is prematurely built for a system that currently executes exactly two shell commands on itself.

The governance framework should be frozen. Do not add to it until the executor can do something real (send a notification, write a daily log, call an API). The value of this framework becomes clear when ARI starts acting — not before.

### 2. Three Overlapping Dashboards

- `ace_career_dashboard.py` — Streamlit career dashboard
- `career_command_center_dashboard.py` — Streamlit career+routing dashboard
- `ari_agent_hub_dashboard.py` — Streamlit agent hub dashboard

All three are read-only diagnostic tools over overlapping SQLite data. One consolidated dashboard would serve the same purpose with less maintenance burden.

### 3. Duplicate ACE Command Center Frontend Structure

`apps/ace_command_center/` and `apps/ace-command-center/` exist as sibling directories. The snake_case one is the Python backend. The kebab-case one is the React frontend. They are the same application split across an inconsistent naming boundary. A reader cannot tell at a glance that these belong together.

---

## What Is Underbuilt

### 1. Daily Use Interface

There is no ritual, hook, or habit for interacting with ARI. The hub exists and works, but there is no morning check-in workflow, no end-of-day reflection prompt, and no notification that pulls you toward the system. You have to choose to open it. Proactive systems don't work that way.

### 2. Automated Scheduler

The orchestration engine never runs on its own. It requires a manual trigger. This means ARI only knows what you've told it at the moment you told it — not what has changed since.

A cron job or launchd agent running `ari-core` orchestration every morning is the single most impactful infrastructure addition.

### 3. Notification Delivery

Signals and alerts are generated, persisted with evidence, and then go nowhere. The delivery path to the operator (macOS notification, terminal print, SMS, anything) does not exist. The alert engine works correctly — it just has no output channel.

### 4. Domain Connectors

ARI needs to ingest state from external systems. Currently there are no connectors for:
- Calendar (what is scheduled today/this week)
- Career system (what actions are pending, what was applied to)
- Health data (movement, sleep)
- Networking CRM (who needs follow-up)
- School (upcoming deadlines, current courses)

Without connectors, ARI only knows what you manually enter. Manual entry is a friction point that kills daily use.

### 5. Memory / Context Retrieval

ARI cannot answer the question "what did I commit to two weeks ago?" or "what open loops have been untouched for 30 days?" There is no query interface that supports natural-language or structured retrieval over historical state. The data model supports this — it just hasn't been built.

---

## What Should Be Removed or Simplified

| Item | Recommendation | Reason |
|---|---|---|
| `~/ARI` (older duplicate) | Archive | Near-identical to `~/ARI(codex)`, missing docs folder |
| `ai_empire/` scripts | Archive | January 2026 prototype, Python 3.9, no integration path |
| Streamlit dashboards (3) | Consolidate to 1 | All read-only, all overlapping. Keep the most useful one. |
| Legacy root-level scripts in openai-dev-sandbox | Classify/archive | `career_agent_basic.py`, `career_command_agent.py`, `career_pipeline.py` marked as LEGACY in manifest |

Do not delete actual data. Only archive/consolidate code.

---

## What Should Become the Core System

**The ARI spine (`~/Code/ari`) is the right architecture.** Do not abandon it or rewrite it. Feed it.

**The immediate priority is domain absorption:**

1. **Career → ARI** (now): Map career daily actions to OpenLoop records. Map current job application status to DailyState next_action. This is one script away.

2. **Daily ritual → DailyState** (this week): Establish a morning check-in habit that writes to ARI. Even a simple CLI form. The data model already supports everything needed.

3. **Networking CRM → ARI module** (1 month): The networking-crm has good bones. Formalize it as `modules/networking-crm` under ARI, give it a Postgres-backed repository, and map contacts/follow-ups to OpenLoop records.

4. **Self-documentation → ARI module** (1 month): The clip/frame/content pipeline should become a formal ARI module that automatically logs orchestration runs, signals, and activity into a structured record. This record feeds the "ARI series" content vision.

5. **Health data → DailyState** (1 month): Even manual daily entry of stress + movement is a start. Later: Apple Health or manual log ingestion.

6. **School → OpenLoop** (when relevant): Deadlines, assignments, and course commitments can be tracked as OpenLoops with project context.

---

## The Philosophical Alignment

The vision is correct and internally consistent. "One intelligence, many quiet processes" maps exactly to the spine architecture: one Postgres database, multiple services reading from the same canonical state, surfaces as windows not sources of truth.

The risk named in `docs/current-state.md` is also correct: "The project can drift into two ARIs if ACE keeps growing its own business logic instead of integrating with canonical ARI." This has already partially happened — the career system is a parallel intelligence, not an extension of ARI.

The corrective doctrine is clear: **Do not expand ACE sideways. Integrate ACE inward.**

Every new domain, module, or automation should be built as an input to the ARI spine, not as a standalone system. This is the only way to reach "full understanding of you."
