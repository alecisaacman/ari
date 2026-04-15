# ARI Execution Intent (v0.9 → v1.0)

## Current State

ARI has:
- canonical brain (ari-core)
- API contract (ari-api)
- hub interface (ari-hub)
- execution layer (file + command + verification)

ARI can:
- mutate files
- run tests/build
- verify outcomes
- persist execution lifecycle

## Problem

ARI executes once, but does not iterate.

It cannot:
- repair failures
- retry intelligently
- improve outputs across attempts
- complete multi-step coding objectives

## Next Objective

Build the **Autonomous Coding Loop Engine**

## Target Behavior

Given:

"Fix failing tests"

ARI should:

1. generate a coding action
2. execute it
3. evaluate result
4. if failed → generate fix
5. repeat until success

## Success Criteria

ARI can:

- run multiple attempts automatically
- improve between attempts
- fix simple failures (syntax, test errors)
- stop intelligently (success or max attempts)
- expose loop state via API
- display loop progress in hub

## Non-Goals (for now)

- full repo reasoning
- complex refactors
- arbitrary shell execution

## Definition of Done

- multi-step loop runs end-to-end
- ARI retries without user input
- at least one real test case passes via loop
- system behaves deterministically
