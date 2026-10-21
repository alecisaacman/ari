# Runtime Execution Convergence Handoff

Date: 2026-10-20
Branch: `claude/execution-convergence`, based on `51c149dd4a22579740b36c438af495ed0c5938fe`

## What changed

The runtime worker loop, the self-improvement runner, verification profiles, the
repo inspector's verification commands, and the legacy controller executor now
reach side effects only through `RuntimeExecutionAdapter`
(`modules/execution/runtime_adapter.py`). Each effectful step is one ARI execution
task, handed to a named worker and dispatched once by
`RecoveredActionGateway.resume_one`. See
[Runtime Execution Convergence](../execution/runtime-convergence.md).

- `ExecutionSessionManager.hand_off_to_worker`: a start-of-task handoff that uses
  the existing continuation packet and acknowledgement path. It is not recorded as
  a worker loss. No schema change.
- `invoke_worker` exists only in the adapter's own tool registry. It is `unbounded`,
  so it is never safe to redispatch.
- Loops stop as `blocked` or `awaiting_approval` when ARI does not dispatch a step,
  and escalate without retrying when a worker's effect is uncertain.
- Verification commands must be explicit command capabilities. A non-capability
  command is refused and counted as a failed check.

## Behavior changes operators will see

- Runtime loops against the live checkout now require `ARI_EXECUTION_ROOT` and
  `ARI_ALLOW_SELF_MODIFICATION=1`. Without them they stop as `blocked`. This is the
  existing execution-authority rule, which these loops previously bypassed.
- The legacy controller (orchestration and approvals) reads and runs commands in
  the configured execution root, not unconditionally in the repository root. With
  no permitted root it returns `execution_root_refused`.
- Global and task pause now stop runtime loops before dispatch.

## Verification

All test runs used a fresh temporary `HOME`, `ARI_HOME`,
`ARI_SURFACE_STATUS_DIR`, `ARI_LOGS_DIR`, and `ARI_STATE_DIR`. A hash and mtime
guard on the live database, the live `current.json`, and the stale runtime data
directory showed no change after any run.

- Full Python suite: 871 passed (858 at baseline, plus 13 new adapter tests)
- Ruff: passed
- `git diff --check`: passed
- Mypy on touched files: no new errors relative to baseline, and the new module is
  clean. The repository-wide strict mypy failure is pre-existing.

Test changes are limited to what convergence requires:

- Three tests used `pytest --version` as a verification command. They now run a
  real test file through the pytest capability.
- Four controller test modules gained a fixture that places the file their
  decisions read inside the configured execution root.

## Still outside the canonical path

- `ExecutionController.run()`: the one-step coding loop and approved retry
  execution
- operator engine actions and the direct execution API/CLI endpoints
- `runtime/playground.py`, the documentation suits, and the career-command adapter

`ExecutionController.run()` is the natural next convergence slice. It already has
ledger checkpoints, but it runs multi-action plans with direct `execute_action`.

## Notes for integration (Codex track)

- Merge test isolation first. The legacy executor now writes canonical ledger rows
  to `core.paths.DB_PATH`, resolved at call time. An unisolated suite run would add
  those rows to the live database.
- `pyproject.toml` does not declare `cryptography` or `requests`, which the suite
  imports. They were installed only in this worktree's venv.
- This branch edits `test_approval_workflow.py`, `test_orchestration_history.py`,
  `test_api_orchestration_history.py`, `test_cli_approvals.py`,
  `test_runtime_repo_inspector.py`, and `test_runtime_self_improvement_runner.py`.
  It does not touch `tests/conftest.py`, the hub helpers, or operator tooling.
