# ARI OpenAI Planner Seam Progress — 2026-04-24

## Status

ARI has a live OpenAI Responses API planner seam in preview/smoke-test form.

## Completed

- Added OpenAI Responses planner adapter.
- Fixed planner import wiring.
- Installed OpenAI SDK locally.
- Added OpenAI SDK dependency to `pyproject.toml`.
- Verified `planner_mode=openai` selects `ModelPlanner`.
- Verified missing API key fallback behavior.
- Added smoke test for simple OpenAI planner response.
- Added real repo-constrained smoke test.
- Confirmed live model returns valid JSON.
- Confirmed local sanity check catches invented targets.
- Confirmed real repo smoke test passed with no invented targets.
- Confirmed no mutation occurred during smoke tests.

## Latest Proven Flow

OpenAI Responses API
  -> ARI planner payload
  -> real repo-constrained planning
  -> valid JSON
  -> local sanity check
  -> no invented action targets
  -> no mutation

## Current Limitation

The OpenAI adapter still relies on loose JSON output plus prompt instructions. This is not sufficient for a durable authority layer.

## Next Target

Phase 3.35: strict schema planner output.

The next implementation should enforce schema-constrained output at the OpenAI boundary and validate the result locally before passing output to `ModelPlanner`.

## Do Not Do Yet

- Do not enable autonomous execution.
- Do not connect GitHub/email/calendar.
- Do not wire avatar/ACE to the planner yet.
- Do not allow broad shell command execution.
