# ARI/ACE Risks and Issues

Audit date: 2026-06-17

---

## Critical Issues

### 1. The Brain Has No Data
**Risk level: Critical**

The ARI spine (`~/Code/ari`) has never been used for daily operation. The Postgres database is empty or contains only test data. All the architecture — state models, signal engine, orchestration runs, alert persistence — operates on nothing.

An AI operating system without operational data cannot detect patterns, surface signals, or learn your context. Every day that passes without real data entry is a day the system falls further behind.

**Immediate action:** Start entering real DailyState and WeeklyState today. Do not build more features before establishing daily use.

---

### 2. No Automatic Scheduling
**Risk level: Critical**

The orchestration engine requires manual triggering. ARI does not run on a schedule. This means:
- Signals are only generated when you remember to run the orchestration command
- Alerts are never proactively surfaced
- The "proactive intelligence" vision is structurally impossible without a scheduler

**Required:** A launchd agent (macOS) or cron job that runs `ari-core` orchestration every morning at a set time.

---

### 3. Alerts Are Generated But Never Delivered
**Risk level: High**

The signal → alert pipeline works correctly. Alerts are persisted to Postgres with structured evidence. They are visible in the hub. But there is no notification delivery path. Alerts sit in the database until you open the hub and look at them.

This is a passive system presenting itself as a proactive one. Until at least one notification channel exists (macOS notification, terminal print at shell startup, Telegram, anything), the alert system provides no real value beyond what you'd notice by opening the hub manually.

---

### 4. Career System Is a Parallel Brain
**Risk level: High**

The career tools in `~/Code/openai-dev-sandbox` are the most active part of the system. They have real data (job scores, daily actions, application packets), real logic (routing, scoring, evaluation), and a real UI. They operate independently of ARI with their own SQLite databases, their own data models, and their own daily action logic.

This creates two sources of truth for your current priorities. ARI doesn't know you applied to a job. Career Command doesn't know your weekly ARI outcomes. They can't signal each other.

The risk named in `docs/current-state.md` has materialized: two ARIs exist.

---

## Structural Issues

### 5. Duplicate Directory: `~/ARI` vs `~/ARI (codex)`
**Risk level: Medium**

`~/ARI` is a near-identical older copy of `~/ARI (codex)`. It has the same content but is missing the `docs/`, `pet-runs/`, and `.playwright-cli/` folders that were added later. There is no git history on either directory to explain the split.

If work is done in `~/ARI` instead of `~/ARI (codex)`, it may overwrite or conflict with the more current version. The correct canonical location is `~/ARI (codex)`.

**Action:** Verify `~/ARI (codex)` is the more complete version, then archive `~/ARI`.

### 6. Two ACE Command Center Backends
**Risk level: Medium**

`apps/ace_command_center/` (Python FastAPI, snake_case) and `apps/ace-command-center/` (React frontend, kebab-case) are the same application's backend and frontend named inconsistently. A reader cannot determine from the directory names alone that they are complementary.

Additionally, there is also an older-style `ace_career_dashboard.py` Streamlit file that partially overlaps with the React frontend. It is marked as `ACTIVE_SUPPORT` in the manifest, which means it is maintained alongside the newer UI.

**Action:** Rename for clarity. Declare one UI as canonical and deprecate the other.

### 7. Three Overlapping Streamlit Dashboards
**Risk level: Low-Medium**

- `ace_career_dashboard.py` — career + safety controls
- `career_command_center_dashboard.py` — career + routing + reporting
- `ari_agent_hub_dashboard.py` — agent hub + career summary

All three read from the same SQLite databases and display overlapping information. Maintaining three dashboards creates three surfaces to update when the data model changes.

**Action:** Choose one as canonical. Archive the others with a note pointing to the canonical one.

### 8. Python Version Not Pinned in openai-dev-sandbox
**Risk level: Medium**

The ARI spine requires Python 3.12 (explicitly stated in pyproject.toml). The openai-dev-sandbox has no pinned Python version. The career tools likely run on whatever Python was installed at the time (possibly 3.11 or 3.13). This creates a split development environment that will cause compatibility issues when absorbing the career module into the spine.

**Action:** Add a `.python-version` or `pyproject.toml` to openai-dev-sandbox specifying the Python version.

### 9. Executor Only Governs Its Own Tests
**Risk level: Medium (strategic)**

The controller/executor framework in `ari-core` is fully implemented — authority evaluation, confidence thresholds, approval workflows, event streams. The actual executor can only:
- Read files within the repo boundary
- Run `pytest -q` or `pytest tests/unit -q`

This means the entire governance framework currently manages running tests on itself. The sophistication of the safety layer is appropriate for a future where ARI sends emails or submits forms. It is disproportionate for a system that can only run pytest.

This is not a bug. It is an early design decision to build safety before capability. But it is a risk if the governance layer is expanded (adding more rules, more approval types) before the executor can do anything real — you will be maintaining a complex system with no observable benefit.

**Action:** Freeze the governance framework. Add executor capabilities before adding governance complexity.

---

## Security Issues

### 10. Sensitive Files — Confirmed Locations
**Risk level: Context-dependent**

The following files contain real credentials. They are gitignored in their respective repositories. Do not change this.

- `~/Code/ari/.env` — Contains Postgres `DATABASE_URL` with password
- `~/Code/openai-dev-sandbox/.env` — Contains `OPENAI_API_KEY`

Both files follow correct practices (gitignored, `.env.example` provided for the spine). Verify the openai-dev-sandbox also has a `.env.example` for the API key pattern. If not, add one.

### 11. FastAPI Backend Has No Authentication
**Risk level: Low (local-only)**

Both FastAPI backends (ari-api and ace_command_center) have no authentication. This is documented and intentional — both are designed for `localhost` only. The ACE manifest explicitly states "Frontend authentication is not implemented. ACE is a local-only app intended for `127.0.0.1`."

This becomes a real risk if either service is ever exposed to a network (home LAN, Tailscale, cloud deploy). Any future non-localhost deployment requires auth before exposure.

---

## Tool Misuse Patterns

### 12. Codex Used as a Content Creation Workspace
**Risk level: Low (historical)**

The `~/ARI` and `~/ARI (codex)` folders contain media artifacts from April 2026 — clips, frames, demos, videos — that appear to have been created during Codex sessions on the ARI workspace. These are ARI self-documentation artifacts, which is a real and intentional use case. However, the artifacts are not organized into a versioned module or integrated with the spine.

This pattern — using a code agent to produce content artifacts that then sit in unstructured folders — will accumulate over time without a structured self-documentation module to capture them.

**Action:** Formalize the self-documentation module so artifacts have a canonical home with metadata.

### 13. ChatGPT-Generated Code Creating Structural Debt
**Risk level: Low-Medium (ongoing)**

Signs of ChatGPT-generated code scattered into the codebase:
- The three overlapping Streamlit dashboards (each added independently, same pattern)
- The `career_pipeline.py`, `career_agent_basic.py`, `career_command_agent.py` files (all marked LEGACY in the manifest after being superseded by a cleaner implementation)
- Root-level `test_*.py` files that are validation scripts rather than pytest suites

Each of these represents a pattern of "ChatGPT suggested this, I added it" without a clear architecture governance step. The result is structural debt that takes more time to clean up than it would have taken to not create.

**Recommendation:** New code from ChatGPT conversations should be treated as a draft, reviewed against the architecture, and placed correctly — not copy-pasted directly into the repository.

---

## Duplication Catalog

| Duplicate | Location 1 | Location 2 | Status |
|---|---|---|---|
| Top-level ARI directory | `~/ARI` | `~/ARI (codex)` | Archive `~/ARI` |
| ACE dashboard UI | `apps/ace-command-center/frontend` | `ace_career_dashboard.py` (Streamlit) | Deprecate Streamlit |
| Career data views | 3× Streamlit dashboards | React frontend | Consolidate |
| Legacy career scripts | `career_pipeline.py` | `career_command_center/` module | Archive legacy |
| Networking state | `~/ARI/modules/networking-crm/state/` | `~/ARI/projects/networking-crm/runtime/state/` | Same DB, two paths |
