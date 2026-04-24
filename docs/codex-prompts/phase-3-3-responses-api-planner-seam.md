# Codex Prompt — Phase 3.3 Responses API Planner Seam

## Role

You are working inside the canonical ARI repo.

Do not redesign ARI. Do not create a second brain. Do not build ACE UI. Do not add autonomous execution.

Your job is to add a narrow OpenAI Responses API planner backend that returns structured plan candidates for ARI to validate.

## Current State

ARI is at approximately 5.8/10.

The repo already includes:

- structured memory blocks
- execution-run capture into session memory
- execution explainability from trace and memory
- persisted ARI self-model memory
- queryable memory context retrieval
- canonical execution tool registry
- memory context wired into execution planning
- execution action validation through the tool registry
- enriched repo context
- CLI/API repo-context inspection
- execution planning preview
- persisted execution plan previews

## Objective

Add a narrow Responses API planner seam.

Given user goal, repo context, memory context, and execution tool registry, return a structured execution plan candidate that ARI validates and persists as a preview.

## Requirements

1. Preserve existing local planner behavior.
2. Add an OpenAI Responses API planner implementation.
3. Require OPENAI_API_KEY from environment.
4. Use strict structured output validation.
5. Return only registered action types.
6. Do not execute actions.
7. Do not write files during planning.
8. Do not run commands during planning.
9. Validate model output through existing execution validation.
10. Persist previews using existing preview infrastructure.
11. Add unit tests with mocked API responses.
12. Add failure tests for malformed model output.
13. Keep implementation small and reversible.

## Schema

The model output must include:

- summary
- confidence
- requires_user_approval
- assumptions
- risks
- actions

Each action must include:

- action_type
- target
- reason
- expected_result
- safety_notes

## Safety Rules

Reject or downgrade the plan if:

- action_type is not in the canonical execution tool registry
- target is outside repo context
- command is not explicitly safe
- model proposes direct execution
- required fields are missing
- output is not valid schema-conforming JSON
- plan is vague or under-specified

## Configuration

Use environment variables:

- OPENAI_API_KEY
- ARI_PLANNER_BACKEND

Suggested values:

- ARI_PLANNER_BACKEND=local
- ARI_PLANNER_BACKEND=openai

Default should remain local unless explicitly set to openai.

## Tests

Add tests for:

- local planner still works
- OpenAI planner builds the correct request payload
- valid model output becomes a plan preview
- invalid output is rejected
- unregistered action type is rejected
- missing API key fails clearly
- no actions are executed during planning

## Verification

Run:

    .venv312/bin/python -m pytest tests/unit -q
    .venv312/bin/python -m ruff check .
    git status

## Non-Goals

- Do not implement safe command execution yet.
- Do not implement autonomous editing.
- Do not integrate GitHub yet.
- Do not integrate email/calendar.
- Do not modify ACE UI.
