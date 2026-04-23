from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..core.paths import DB_PATH, PROJECT_ROOT
from ..modules.coordination.db import put_coordination_entity
from .codex_adapter import CodexAdapter, CodexInvocationResult
from .response_contract import build_cli_response, render_cli_response


@dataclass(frozen=True, slots=True)
class LoopControl:
    status: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LoopRunnerResult:
    loop_id: str
    goal: str
    status: str
    reason: str
    cycles_run: int
    worker_runs: list[CodexInvocationResult]
    persisted_loop: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "loopId": self.loop_id,
            "goal": self.goal,
            "status": self.status,
            "reason": self.reason,
            "cyclesRun": self.cycles_run,
            "workerRuns": [run.to_dict() for run in self.worker_runs],
            "persistedLoop": self.persisted_loop,
        }


class LoopRunner:
    def __init__(
        self,
        *,
        adapter: CodexAdapter | None = None,
        db_path: Path = DB_PATH,
    ) -> None:
        self.adapter = adapter or CodexAdapter()
        self.db_path = db_path

    def run(
        self,
        goal: str,
        *,
        max_cycles: int = 1,
        cwd: Path | str | None = None,
        prepared_prompt: str | None = None,
    ) -> LoopRunnerResult:
        if not goal.strip():
            raise ValueError("goal is required")
        if max_cycles < 1:
            raise ValueError("max_cycles must be at least 1")

        loop_id = f"runtime-loop-{uuid4()}"
        resolved_cwd = Path(cwd or PROJECT_ROOT).expanduser().resolve()
        worker_runs: list[CodexInvocationResult] = []
        persisted_worker_runs: list[dict[str, object]] = []
        control = LoopControl(status="escalate", reason="The loop did not produce a usable worker result.")

        for cycle_index in range(1, max_cycles + 1):
            prompt = _build_prompt(
                goal,
                previous_run=worker_runs[-1] if worker_runs else None,
                cycle_index=cycle_index,
                prepared_prompt=prepared_prompt,
            )
            invocation = self.adapter.invoke(prompt, cwd=resolved_cwd)
            worker_runs.append(invocation)
            persisted_worker_runs.append(
                self._persist_worker_run(loop_id=loop_id, cycle_index=cycle_index, prompt=prompt, result=invocation)
            )
            control = _evaluate_worker_result(invocation, cycle_index=cycle_index, max_cycles=max_cycles)
            if control.status != "retry":
                break

        persisted_loop = self._persist_loop_record(
            loop_id=loop_id,
            goal=goal,
            control=control,
            max_cycles=max_cycles,
            worker_runs=worker_runs,
            persisted_worker_runs=persisted_worker_runs,
        )
        return LoopRunnerResult(
            loop_id=loop_id,
            goal=goal,
            status=control.status,
            reason=control.reason,
            cycles_run=len(worker_runs),
            worker_runs=worker_runs,
            persisted_loop=persisted_loop,
        )

    def _persist_worker_run(
        self,
        *,
        loop_id: str,
        cycle_index: int,
        prompt: str,
        result: CodexInvocationResult,
    ) -> dict[str, object]:
        return _row_to_plain_dict(
            put_coordination_entity(
                "runtime_worker_run",
                {
                    "id": f"runtime-worker-run-{uuid4()}",
                    "loop_id": loop_id,
                    "cycle_index": cycle_index,
                    "prompt": prompt,
                    "backend": result.backend,
                    "command_json": json.dumps(result.command),
                    "cwd": result.cwd,
                    "success": 1 if result.success else 0,
                    "retryable": 1 if result.retryable else 0,
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "created_at": _now_iso(),
                },
                db_path=self.db_path,
            )
        )

    def _persist_loop_record(
        self,
        *,
        loop_id: str,
        goal: str,
        control: LoopControl,
        max_cycles: int,
        worker_runs: list[CodexInvocationResult],
        persisted_worker_runs: list[dict[str, object]],
    ) -> dict[str, object]:
        last_run = worker_runs[-1] if worker_runs else None
        last_worker_run_id = None if not persisted_worker_runs else persisted_worker_runs[-1]["id"]
        return _row_to_plain_dict(
            put_coordination_entity(
                "runtime_loop_record",
                {
                    "id": loop_id,
                    "goal": goal,
                    "status": control.status,
                    "reason": control.reason,
                    "cycles_run": len(worker_runs),
                    "max_cycles": max_cycles,
                    "final_output": "" if last_run is None else last_run.stdout,
                    "final_error": "" if last_run is None else last_run.stderr,
                    "last_worker_run_id": last_worker_run_id,
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                },
                db_path=self.db_path,
            )
        )


def run_goal_loop(
    goal: str,
    *,
    max_cycles: int = 1,
    cwd: Path | str | None = None,
    db_path: Path = DB_PATH,
    adapter: CodexAdapter | None = None,
    prepared_prompt: str | None = None,
) -> LoopRunnerResult:
    runner = LoopRunner(adapter=adapter, db_path=db_path)
    return runner.run(goal, max_cycles=max_cycles, cwd=cwd, prepared_prompt=prepared_prompt)


def handle_runtime_codex_loop(args, db_path: Path = DB_PATH) -> int:
    result = run_goal_loop(
        args.goal,
        max_cycles=args.max_cycles,
        cwd=args.cwd,
        db_path=db_path,
    )
    response = build_cli_response(
        goal=args.goal,
        route="codex_loop",
        route_reason="The request explicitly invoked the bounded Codex worker loop.",
        result=result.to_dict(),
    )
    print(render_cli_response(response))
    return 0


def _build_prompt(
    goal: str,
    *,
    previous_run: CodexInvocationResult | None,
    cycle_index: int,
    prepared_prompt: str | None = None,
) -> str:
    if previous_run is None and prepared_prompt is not None:
        return prepared_prompt
    if previous_run is None:
        return (
            "You are a coding worker being invoked by ARI.\n"
            f"Goal: {goal}\n"
            "Work locally, keep the change minimal, and report what you changed plus verification."
        )

    return (
        "You are a coding worker being reinvoked by ARI after the previous attempt did not finish cleanly.\n"
        f"Goal: {goal}\n"
        f"Previous stderr: {previous_run.stderr[:800]}\n"
        f"Previous stdout: {previous_run.stdout[:800]}\n"
        "Refine the approach, keep the change minimal, and report the outcome clearly."
    )


def _evaluate_worker_result(
    result: CodexInvocationResult,
    *,
    cycle_index: int,
    max_cycles: int,
) -> LoopControl:
    if result.success and result.stdout.strip():
        return LoopControl(status="stop", reason="Codex returned a usable result.")
    if result.retryable and cycle_index < max_cycles:
        return LoopControl(status="retry", reason="Codex failed in a retryable way; another bounded pass is allowed.")
    if result.success and not result.stdout.strip():
        return LoopControl(status="escalate", reason="Codex exited successfully but returned no usable output.")
    return LoopControl(status="escalate", reason="Codex did not produce a usable result within the bounded loop.")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _row_to_plain_dict(row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}
