You are an autonomous senior software engineer and system architect.

Your objective is to upgrade ARI from a single-step execution system into a multi-step autonomous coding loop capable of iterating until success.

Goal:
Build the ARI Autonomous Coding Loop Engine.

Requirements:
- sit above the existing execution module
- use ari-core as canonical execution brain
- use ari-api as contract
- use ari-hub as surface only

System behavior:
1. take a coding goal
2. generate a coding action
3. execute it
4. evaluate result
5. if failed, analyze failure
6. generate next fix action
7. repeat until success or max attempts

Build:
- coding_loop engine in ari-core
- action generator
- failure analyzer
- retry policy
- API endpoint: POST /coding-loop/run
- canonical storage for loop state and attempts
- calm hub display of loop state

Validation:
- failing test -> ARI fixes it
- syntax error -> ARI repairs it
- loop stops after max attempts

This is the layer that moves ARI from executor to builder.
Proceed.
