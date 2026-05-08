# Career Command Adapter

Career Command remains the existing working prototype at:

```text
~/code/openai-dev-sandbox
```

ARI does not copy, recreate, or migrate the job-search engine in this slice. The
adapter is a thin bridge that lets ARI inspect local Career Command state and run
a fixed set of safe Career Command scripts.

## Adapter Role

The adapter package lives at:

```text
packages/ari-career-command/src/ari_career_command/
```

It reads `CAREER_COMMAND_ROOT` when set and otherwise defaults to
`~/code/openai-dev-sandbox`.

It detects the sandbox Python at:

```text
~/code/openai-dev-sandbox/.venv/bin/python
```

The adapter can inspect:

- `data/career_tracker.csv`
- `pending_actions/`
- `approved_actions/`
- `rejected_actions/`
- `reports/scout_reports/latest.md`
- `reports/job_evaluations/latest_batch_summary.csv`
- `ace_career_dashboard.py`

The adapter can run only these controlled commands:

```text
career_scout.py
tools/scout_report_to_jobs.py
tools/batch_evaluate_jobs.py --limit 5
```

The daily scout preview runs those three commands in order and stops for human
review. If one command fails, later dependent commands are not run.

## Telegram Commands

The Telegram Gateway handles authorized private messages to `@AriCommandBot`
with these commands:

```text
/career status
/career tracker
/career pending
/career latest
/career dashboard
/career scout_preview
```

`/career status` reports sandbox availability, tracker count, pending count,
approved/rejected counts, and whether the latest scout and batch summary files
exist.

`/career tracker` returns the top tracked opportunities from
`data/career_tracker.csv`, ranked by `overall_score`.

`/career pending` lists local pending action draft filenames and titles.

`/career latest` summarizes the latest scout report and the latest batch
evaluation summary.

`/career dashboard` returns the local Streamlit dashboard URL and the command to
run it.

`/career scout_preview` runs the controlled scout preview:

```text
career_scout.py
tools/scout_report_to_jobs.py
tools/batch_evaluate_jobs.py --limit 5
```

It returns command status plus the latest batch summary, then stops for review.

## Safety Boundaries

The adapter and Telegram route do not:

- send emails
- send LinkedIn messages
- apply to jobs
- contact anyone externally
- save evaluated jobs into the tracker
- draft outreach
- approve pending actions
- expose API keys
- read `.env`
- accept arbitrary shell commands from Telegram

Career Command scripts may use their own existing environment when invoked, but
ARI does not read or expose the sandbox `.env`.

Any external action remains outside this adapter and must stay a local pending
draft until explicit human approval.

## Future Migration Plan

This slice intentionally preserves Career Command as an external working system.
Future migration should happen only after the integration behavior is useful and
stable from ARI/ACE surfaces.

Clean migration steps later:

1. Keep the Telegram command contract stable.
2. Move durable Career Command state into canonical ARI schemas.
3. Move read models before moving write flows.
4. Preserve explicit approval state for any external-facing action.
5. Replace sandbox script calls with canonical ARI tools one capability at a
   time.

Until then, the adapter remains the bridge and Career Command remains the job
search engine.
