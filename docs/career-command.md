# Career Command

Career Command is ARI's first high-stakes proof module. Its current objective is
simple: get Alec hired.

ARI owns orchestration, state visibility, safety rules, and future memory hooks.
Career Command owns the job-search workflow state: scouting, evaluation, local
tracking, local drafts, and local approval/rejection state. Telegram and
dashboards are ACE surfaces over this module; they must not become separate
brains.

## Current Integration

The working Career Command prototype remains external at:

```text
~/code/openai-dev-sandbox
```

ARI reads that prototype through the adapter package:

```text
packages/ari-career-command/src/ari_career_command/
```

The adapter defaults to `~/code/openai-dev-sandbox` and can be pointed elsewhere
with `CAREER_COMMAND_ROOT` or `--root`.

The local read model inspects:

- `data/career_tracker.csv`
- `pending_actions/`
- `approved_actions/`
- `rejected_actions/`
- `logs/action_log.csv`
- `reports/scout_reports/latest.md`
- `reports/job_evaluations/latest_batch_summary.csv`
- recent files under `reports/`

## Local Commands

Run the full operating view:

```text
ari career command-center
```

Read specific slices:

```text
ari career status
ari career pending
ari career next
ari career tracker
ari career reports
ari career command-center --json
```

Optional safe preview:

```text
ari career scout-preview
```

`scout-preview` is allowed to run only the existing safe preview pipeline and
then stop for review. It does not save jobs, create outreach drafts, approve
anything, apply, send messages, or contact anyone.

Every local Career Command operation writes the canonical ARI surface status
artifact through the existing surface status layer. It does not create a second
status system.

## Future Telegram Contract

| Local command | Future Telegram command | Output shape | Safety level |
| --- | --- | --- | --- |
| `ari career status` | `/career status` | sandbox, tracker, pending, report availability | read-only |
| `ari career pending` | `/career pending` | pending local drafts requiring review | read-only |
| `ari career next` | `/career next` | recommended next actions | read-only |
| `ari career tracker` | `/career tracker` | tracker totals, status buckets, top roles | read-only |
| `ari career reports` | `/career reports` | latest scout, batch summary, recent report files | read-only |
| `ari career scout-preview` | `/career scout_preview` | safe scout/evaluation preview result | local preview only |

Telegram may later expose local save, draft, approve, and reject operations, but
external sending must remain outside this adapter unless explicitly approved
through a governed approval flow.

## Safety Boundaries

Career Command may:

- scout
- summarize
- evaluate
- rank
- save locally
- draft locally
- recommend
- mark local approval/rejection state

Career Command may not:

- submit applications automatically
- send emails automatically
- send LinkedIn messages automatically
- contact people automatically
- mutate external systems without explicit approval
- expose secrets or read `.env` into ARI outputs
- accept arbitrary shell execution from Telegram or other surfaces

## Known Limitations

- The durable job-search engine still lives in `~/code/openai-dev-sandbox`.
- The ARI command center is currently a read model plus safe wrappers, not the
  final canonical Career Command database.
- `scout-preview` may fail if the external prototype is missing dependencies or
  API quota. The status, pending, tracker, reports, and command-center commands
  do not require API calls.
- The next-action recommender is deterministic and intentionally conservative.

## Next Build Priorities

1. Add a canonical saved-target/action schema once the external workflow proves
   stable from ARI surfaces.
2. Expose the read-only commands through Telegram using the documented command
   contract.
3. Add governed local approve/reject flows to ARI state before any external send
   path is considered.
