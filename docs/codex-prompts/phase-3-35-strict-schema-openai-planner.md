# Codex Prompt — Phase 3.35 Strict Schema OpenAI Planner Output

## Role

You are working inside the canonical ARI repo.

Do not redesign ARI. Do not build ACE UI. Do not add autonomous execution. Do not add GitHub, email, calendar, or broad filesystem integrations.

Your job is to harden the OpenAI Responses planner seam by replacing loose JSON output with strict schema-constrained planner output and local validation.

## Current State

ARI now has:

- CLI help/introspection guard
- OpenAI Responses planner adapter
- planner_mode=openai selecting ModelPlanner
- live OpenAI planner smoke test
- real repo-constrained OpenAI planner smoke test
- OpenAI SDK captured in pyproject.toml
- no mutation during smoke tests
- sanity check proving no invented action targets in the real-repo smoke test

Current known issue:

The adapter currently relies on loose json_object output plus prompt instructions. This is not strong enough for ARI's authority layer.

## Objective

Upgrade the OpenAI planner adapter to enforce a strict planner output schema before returning model output to ModelPlanner.

## Requirements

1. Define a strict planner output schema.
2. Use the schema in the OpenAI Responses API request.
3. Validate returned JSON locally before returning it to ModelPlanner.
4. Fail closed on malformed output.
5. Preserve planner_mode=openai selection behavior.
6. Preserve safe fallback behavior when OpenAI cannot be configured.
7. Do not execute actions.
8. Do not modify files as part of planning.
9. Do not add broad shell command execution.
10. Keep implementation small and testable.

## Expected Planner Output Shape

The planner output should include:

- confidence: number between 0 and 1
- summary: string
- assumptions: list[string]
- risks: list[string]
- actions: list[action]
- verification: list[verification]

Each action should include:

- type: string
- path_or_command: string
- reason: string
- safety_notes: list[string]

Each verification item should include:

- type: string
- command: string

## Validation Rules

Reject output if:

- required fields are missing
- confidence is not a number between 0 and 1
- actions is not a list
- verification is not a list
- action target is missing
- action reason is vague or empty
- model returns markdown
- model returns invalid JSON
- model proposes unregistered or disallowed action types
- model invents files/commands not provided in the planner payload

## Tests

Add mocked tests for:

- valid OpenAI structured output
- invalid JSON
- missing required fields
- confidence outside range
- invented file target
- invented command target
- missing API key fallback
- no actions executed during planning

## Verification

Run:

    .venv312/bin/python -m pytest tests/unit -q
    .venv312/bin/python -m ruff check services/ari-core/src/ari_core/modules/execution/openai_responses.py services/ari-core/src/ari_core/modules/execution/planners.py
    .venv312/bin/python scripts/dev/smoke_openai_planner.py
    .venv312/bin/python scripts/dev/smoke_openai_real_repo_plan.py
    git status

## Suggested Commit Messages

1. Add strict schema for OpenAI planner output
2. Validate OpenAI planner output locally
3. Test strict OpenAI planner schema handling
4. Update OpenAI planner smoke tests

## Non-Goals

- Do not implement safe command execution.
- Do not implement autonomous file editing.
- Do not connect GitHub.
- Do not connect email/calendar.
- Do not modify ACE/avatar UI.
