# ARI Demo Findings — 2026-04-24

## Demo Result

The demo partially succeeded and exposed an important CLI design gap.

## What Worked

- `tests/unit/test_execution_controller.py` passed with 19 tests.
- Execution controller planning/preview behavior is test-backed.
- ARI captured failed Codex worker runs into structured runtime loop records.
- ARI surfaced Codex usage-limit failures cleanly.
- ARI returned structured terminal contract output.
- ARI demonstrated route behavior:
  - implementation-like requests routed to `codex_loop`
  - planning-like requests routed to `plan_only`

## What Failed

CLI help commands were incorrectly interpreted as natural-language goals.

Examples:

- `python -m ari_core.ari --help`
- `python -m ari_core.ari execution --help`
- `python -m ari_core.ari execution context --help`

These were routed into the Codex worker loop instead of returning local help.

## Design Gap

ARI currently has a real terminal surface, but not a clean developer command-mode CLI.

The command surface should distinguish:

- local CLI commands
- help/introspection commands
- natural-language goals
- Codex worker loops
- plan-only requests

## Required Fix

Add a CLI guard so help/introspection commands never invoke Codex.

At minimum, handle:

- `--help`
- `-h`
- `help`
- `execution --help`
- `execution help`
- `execution context --help`
- `execution plans --help`

## Strategic Impact

This matters before the Responses API planner seam because ARI should not waste external API calls on local help/introspection commands.

## Next Build Queue

1. Add CLI help/introspection guard.
2. Add tests proving help commands do not route to Codex.
3. Continue Phase 3.3 Responses API planner seam.
