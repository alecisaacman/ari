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
- Added strict schema-constrained OpenAI planner output.
- Added local strict output validation before handing output to `ModelPlanner`.
- Added canonical safe command policy for verification command validation.

## Latest Proven Flow

OpenAI Responses API
  -> ARI planner payload
  -> strict schema-constrained planner output
  -> local output validation
  -> command policy check for verification commands
  -> no mutation

## Current Boundary

The OpenAI adapter does not execute actions. The command policy validates proposed
verification commands only. Command execution remains disabled until a future
approval boundary exists.

## Next Target

Phase 3.5: approval-bound verification loops.

The next implementation should decide how a validated command becomes eligible
for explicit approval and later execution without weakening ARI's authority layer.

## Do Not Do Yet

- Do not enable autonomous execution.
- Do not connect GitHub/email/calendar.
- Do not wire avatar/ACE to the planner yet.
- Do not allow broad shell command execution.
