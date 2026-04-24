from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...core.paths import DB_PATH
from ..coordination.db import put_coordination_entity
from ..memory.context import build_memory_context
from .executor import execute_action
from .models import (
    ExecutionGoal,
    ExecutionRun,
    FailureContext,
    PlannerResult,
    RepoContext,
    VerificationExpectation,
    WorkerAction,
    WorkerDecision,
    WorkerPlan,
    _now_iso,
)
from .planners import (
    MAX_PLAN_ACTIONS,
    ExecutionPlanner,
    RuleBasedPlanner,
    resolve_execution_planner,
)
from .sandbox import ExecutionRoot
from .tools import get_execution_tool_registry


def build_repo_context(repo_root: Path | str | None = None) -> RepoContext:
    root = ExecutionRoot(repo_root).root
    changed_paths, git_available = _git_changed_paths(root)
    current_branch = _git_current_branch(root) if git_available else None
    files_sample = tuple(_files_sample(root))
    package_manifests = tuple(_package_manifests(files_sample))
    return RepoContext(
        repo_root=str(root),
        git_available=git_available,
        git_dirty=bool(changed_paths),
        changed_paths=tuple(changed_paths),
        current_branch=current_branch,
        files_sample=files_sample,
        directories_sample=tuple(_directories_sample(root)),
        package_manifests=package_manifests,
        test_commands=tuple(_test_commands(package_manifests, files_sample)),
        language_summary=_language_summary(files_sample),
    )


def decide_worker_action(
    goal: ExecutionGoal,
    repo_context: RepoContext,
    *,
    cycle_index: int,
    previous_results: Sequence[dict[str, Any]] = (),
) -> WorkerDecision:
    if previous_results and _last_result_succeeded(previous_results):
        return WorkerDecision(
            status="stop",
            reason="The previous action verified successfully.",
            confidence=0.95,
            cycle_index=cycle_index,
            planner_name="rule_based",
        )
    planner_result = RuleBasedPlanner().plan(goal, repo_context)
    return _decision_from_planner_result(planner_result, cycle_index)


class ExecutionController:
    def __init__(
        self,
        *,
        execution_root: Path | str | None = None,
        db_path: Path = DB_PATH,
        planner: ExecutionPlanner | None = None,
        planner_mode: str | None = None,
        planner_completion_fn: Callable[[dict[str, object]], str] | None = None,
        memory_context_layers: list[str] | None = None,
        memory_context_limit: int = 5,
    ) -> None:
        self.execution_root = ExecutionRoot(execution_root)
        self.db_path = db_path
        self.memory_context_layers = memory_context_layers or [
            "self_model",
            "long_term",
            "session",
        ]
        self.memory_context_limit = memory_context_limit
        self.tool_registry = get_execution_tool_registry()
        self.planner, self.planner_selection = resolve_execution_planner(
            planner=planner,
            planner_mode=planner_mode,
            completion_fn=planner_completion_fn,
        )

    def plan(self, goal: ExecutionGoal | str) -> dict[str, Any]:
        execution_goal = goal if isinstance(goal, ExecutionGoal) else ExecutionGoal(objective=goal)
        if execution_goal.max_cycles < 1:
            raise ValueError("max_cycles must be at least 1")

        context = build_repo_context(self.execution_root.root)
        memory_context = self._build_memory_context(execution_goal)
        planner_result = self.planner.plan(
            execution_goal,
            context,
            failure_context=None,
            memory_context=memory_context,
        )
        decision = _decision_from_planner_result(planner_result, cycle_index=1)
        validation_error = (
            None if decision.plan is None else self._validate_plan(decision.plan)
        )
        return {
            "goal": execution_goal.to_dict(),
            "status": _preview_status(decision, validation_error),
            "reason": validation_error or decision.reason,
            "repo_context": context.to_dict(),
            "memory_context": memory_context,
            "planner_config": self.planner_selection.to_dict(),
            "planner_result": planner_result.to_dict(),
            "decision": decision.to_dict(),
            "validation_error": validation_error,
            "created_at": _now_iso(),
        }

    def run(self, goal: ExecutionGoal | str) -> ExecutionRun:
        execution_goal = goal if isinstance(goal, ExecutionGoal) else ExecutionGoal(objective=goal)
        if execution_goal.max_cycles < 1:
            raise ValueError("max_cycles must be at least 1")

        run_id = f"execution-run-{uuid4()}"
        created_at = _now_iso()
        contexts: list[RepoContext] = []
        decisions: list[WorkerDecision] = []
        results: list[dict[str, Any]] = []
        status = "failed"
        reason = "Execution did not run."
        failure_context: FailureContext | None = None
        planner_config = self.planner_selection.to_dict()

        for cycle_index in range(1, execution_goal.max_cycles + 1):
            context = build_repo_context(self.execution_root.root)
            memory_context = self._build_memory_context(execution_goal)
            contexts.append(context)
            planner_result = self.planner.plan(
                execution_goal,
                context,
                failure_context=failure_context,
                memory_context=memory_context,
            )
            decision = _decision_from_planner_result(planner_result, cycle_index)
            decisions.append(decision)

            if decision.status == "stop":
                status = "completed"
                reason = decision.reason
                break

            if decision.status == "reject" or decision.plan is None:
                results.append(
                    _rejected_result(
                        planner_result,
                        decision.reason,
                        planner_config=planner_config,
                        memory_context=memory_context,
                    )
                )
                status = "rejected"
                reason = decision.reason
                break

            plan = decision.plan
            validation_error = self._validate_plan(plan)
            if validation_error is not None:
                result = {
                    "success": False,
                    "verified": False,
                    "retryable": False,
                    "error": validation_error,
                    "plan": plan.to_dict(),
                    "planner": planner_result.planner_name,
                    "confidence": planner_result.confidence,
                    "failure_context": (
                        None if failure_context is None else failure_context.to_dict()
                    ),
                    "planner_config": planner_config,
                    "memory_context": memory_context,
                }
                results.append(result)
                status = "rejected"
                reason = validation_error
                break

            result = self._execute_plan(plan)
            result["planner"] = planner_result.planner_name
            result["confidence"] = planner_result.confidence
            result["failure_context"] = (
                None if failure_context is None else failure_context.to_dict()
            )
            result["planner_config"] = planner_config
            result["memory_context"] = memory_context
            results.append(result)

            if result["verified"]:
                status = "completed"
                reason = "Action executed and verification passed."
                break

            if cycle_index < execution_goal.max_cycles:
                failure_context = FailureContext(
                    cycle_index=cycle_index,
                    reason="Plan verification failed.",
                    result=result,
                )
                status = "exhausted" if result["retryable"] else "failed"
                reason = "Plan verification failed; retry planning is allowed."
                continue

            if result["retryable"]:
                status = "exhausted"
                reason = "Retryable execution failed until max_cycles was exhausted."
                break

            if not result["retryable"]:
                status = "failed"
                reason = "Action failed verification and is not retryable."
                break

        updated_at = _now_iso()
        run = ExecutionRun(
            id=run_id,
            goal=execution_goal,
            status=status,
            reason=reason,
            cycles_run=len(decisions),
            repo_contexts=tuple(contexts),
            decisions=tuple(decisions),
            results=tuple(results),
            created_at=created_at,
            updated_at=updated_at,
            planner_config=planner_config,
        )
        persisted = self._persist_run(run)
        return ExecutionRun(
            id=run.id,
            goal=run.goal,
            status=run.status,
            reason=run.reason,
            cycles_run=run.cycles_run,
            repo_contexts=run.repo_contexts,
            decisions=run.decisions,
            results=run.results,
            created_at=run.created_at,
            updated_at=run.updated_at,
            planner_config=run.planner_config,
            persisted_run=persisted,
        )

    def _validate_action(self, action: WorkerAction) -> str | None:
        if action.requires_approval:
            return "Action requires approval and cannot run automatically."
        return self.tool_registry.validate_execution_action(
            action.to_execution_action(),
            execution_root=self.execution_root,
        )

    def _build_memory_context(self, goal: ExecutionGoal) -> dict[str, object]:
        return build_memory_context(
            goal.objective,
            layers=self.memory_context_layers,
            limit=self.memory_context_limit,
            db_path=self.db_path,
        )

    def _validate_plan(self, plan: WorkerPlan) -> str | None:
        if not plan.actions:
            return "Execution plans require at least one action."
        if len(plan.actions) > MAX_PLAN_ACTIONS:
            return f"Execution plans are bounded to {MAX_PLAN_ACTIONS} actions."
        for action in plan.actions:
            validation_error = self._validate_action(action)
            if validation_error is not None:
                return validation_error
        return None

    def _execute_plan(self, plan: WorkerPlan) -> dict[str, Any]:
        action_results: list[dict[str, Any]] = []
        for action in plan.actions:
            action_result = execute_action(
                action.to_execution_action(),
                execution_root=self.execution_root.root,
            )
            action_verified = self._verify_action(action, action_result)
            normalized_result = {
                **action_result,
                "verified": action_verified,
                "retryable": _result_retryable(action_result),
                "action": action.to_execution_action(),
            }
            action_results.append(normalized_result)
            if not action_verified:
                break

        expectation_results = [
            self._verify_expectation(expectation) for expectation in plan.verification
        ]
        success = all(bool(item.get("success")) for item in action_results)
        verified = (
            bool(action_results)
            and all(bool(item.get("verified")) for item in action_results)
            and all(bool(item.get("verified")) for item in expectation_results)
        )
        retryable = any(bool(item.get("retryable")) for item in action_results)
        first = action_results[0] if len(action_results) == 1 else {}
        return {
            **first,
            "success": success,
            "verified": verified,
            "retryable": retryable,
            "plan": plan.to_dict(),
            "action_results": action_results,
            "verification_results": expectation_results,
        }

    def _verify_action(self, action: WorkerAction, result: dict[str, Any]) -> bool:
        if not bool(result.get("success")):
            return False
        payload = action.to_execution_action()
        if action.action_type == "write_file":
            resolved = self.execution_root.resolve_path(str(payload["path"]))
            return resolved.read_text(encoding="utf-8") == str(payload["content"])
        if action.action_type == "patch_file":
            resolved = self.execution_root.resolve_path(str(payload["path"]))
            return str(payload["replace"]) in resolved.read_text(encoding="utf-8")
        return True

    def _verify_expectation(self, expectation: VerificationExpectation) -> dict[str, Any]:
        try:
            if expectation.expectation_type == "action_success":
                return {
                    "verified": True,
                    "expectation": expectation.to_dict(),
                }
            resolved = self.execution_root.resolve_path(expectation.target)
            if expectation.expectation_type == "path_exists":
                return {
                    "verified": resolved.exists(),
                    "expectation": expectation.to_dict(),
                }
            if expectation.expectation_type == "file_content":
                actual = resolved.read_text(encoding="utf-8")
                return {
                    "verified": actual == expectation.expected,
                    "expectation": expectation.to_dict(),
                }
        except (OSError, ValueError) as error:
            return {
                "verified": False,
                "error": str(error),
                "expectation": expectation.to_dict(),
            }
        return {
            "verified": False,
            "error": f"Unsupported verification expectation: {expectation.expectation_type}",
            "expectation": expectation.to_dict(),
        }

    def _persist_run(self, run: ExecutionRun) -> dict[str, object]:
        row = put_coordination_entity(
            "runtime_execution_run",
            {
                "id": run.id,
                "goal_id": run.goal.id,
                "objective": run.goal.objective,
                "status": run.status,
                "reason": run.reason,
                "cycles_run": run.cycles_run,
                "max_cycles": run.goal.max_cycles,
                "repo_root": (
                    run.repo_contexts[-1].repo_root
                    if run.repo_contexts
                    else str(self.execution_root.root)
                ),
                "contexts_json": json.dumps([context.to_dict() for context in run.repo_contexts]),
                "decisions_json": json.dumps([decision.to_dict() for decision in run.decisions]),
                "results_json": json.dumps(list(run.results)),
                "created_at": run.created_at,
                "updated_at": run.updated_at,
            },
            db_path=self.db_path,
        )
        return {key: row[key] for key in row.keys()}


def run_execution_goal(
    goal: ExecutionGoal | str,
    *,
    execution_root: Path | str | None = None,
    db_path: Path = DB_PATH,
    planner: ExecutionPlanner | None = None,
    planner_mode: str | None = None,
    planner_completion_fn: Callable[[dict[str, object]], str] | None = None,
    memory_context_layers: list[str] | None = None,
    memory_context_limit: int = 5,
) -> ExecutionRun:
    return ExecutionController(
        execution_root=execution_root,
        db_path=db_path,
        planner=planner,
        planner_mode=planner_mode,
        planner_completion_fn=planner_completion_fn,
        memory_context_layers=memory_context_layers,
        memory_context_limit=memory_context_limit,
    ).run(goal)


def plan_execution_goal(
    goal: ExecutionGoal | str,
    *,
    execution_root: Path | str | None = None,
    db_path: Path = DB_PATH,
    planner: ExecutionPlanner | None = None,
    planner_mode: str | None = None,
    planner_completion_fn: Callable[[dict[str, object]], str] | None = None,
    memory_context_layers: list[str] | None = None,
    memory_context_limit: int = 5,
) -> dict[str, Any]:
    return ExecutionController(
        execution_root=execution_root,
        db_path=db_path,
        planner=planner,
        planner_mode=planner_mode,
        planner_completion_fn=planner_completion_fn,
        memory_context_layers=memory_context_layers,
        memory_context_limit=memory_context_limit,
    ).plan(goal)


def _decision_from_planner_result(
    planner_result: PlannerResult,
    cycle_index: int,
) -> WorkerDecision:
    plan = planner_result.plan
    return WorkerDecision(
        status=planner_result.status,
        reason=planner_result.reason,
        confidence=planner_result.confidence,
        cycle_index=cycle_index,
        action=None if plan is None or not plan.actions else plan.actions[0],
        plan=plan,
        planner_name=planner_result.planner_name,
        failure_context=planner_result.failure_context,
    )


def _rejected_result(
    planner_result: PlannerResult,
    reason: str,
    *,
    planner_config: dict[str, Any],
    memory_context: dict[str, object],
) -> dict[str, Any]:
    return {
        "success": False,
        "verified": False,
        "retryable": False,
        "error": reason,
        "planner": planner_result.planner_name,
        "confidence": planner_result.confidence,
        "failure_context": (
            None
            if planner_result.failure_context is None
            else planner_result.failure_context.to_dict()
        ),
        "planner_config": planner_config,
        "memory_context": memory_context,
    }


def _preview_status(decision: WorkerDecision, validation_error: str | None) -> str:
    if validation_error is not None:
        return "invalid"
    if decision.status == "act":
        return "planned"
    if decision.status == "stop":
        return "stopped"
    return "rejected"


def _git_changed_paths(repo_root: Path) -> tuple[list[str], bool]:
    try:
        completed = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return [], False
    if completed.returncode != 0:
        return [], False
    return [line[3:].strip() for line in completed.stdout.splitlines() if line.strip()], True


def _git_current_branch(repo_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    branch = completed.stdout.strip()
    if completed.returncode != 0:
        return None
    return branch or None


SKIPPED_REPO_DIRS = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "runtime",
    "venv",
}

PACKAGE_MANIFEST_NAMES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
    "uv.lock",
}

LANGUAGE_EXTENSIONS = {
    ".css": "css",
    ".html": "html",
    ".js": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".py": "python",
    ".sh": "shell",
    ".ts": "typescript",
    ".tsx": "typescript",
}


def _files_sample(repo_root: Path, limit: int = 50) -> list[str]:
    return [
        path.relative_to(repo_root).as_posix()
        for path in _iter_repo_files(repo_root)
        if path.name != ".DS_Store"
    ][:limit]


def _directories_sample(repo_root: Path, limit: int = 25) -> list[str]:
    directories: list[str] = []
    for path in _iter_repo_paths(repo_root):
        if not path.is_dir() or path == repo_root:
            continue
        relative = path.relative_to(repo_root).as_posix()
        if any(part in SKIPPED_REPO_DIRS for part in path.relative_to(repo_root).parts):
            continue
        directories.append(relative)
        if len(directories) >= limit:
            break
    return directories


def _package_manifests(files_sample: tuple[str, ...]) -> list[str]:
    return [path for path in files_sample if Path(path).name in PACKAGE_MANIFEST_NAMES]


def _test_commands(
    package_manifests: tuple[str, ...],
    files_sample: tuple[str, ...],
) -> list[tuple[str, ...]]:
    commands: list[tuple[str, ...]] = []
    manifest_names = {Path(path).name for path in package_manifests}
    if "pyproject.toml" in manifest_names or any(path.endswith(".py") for path in files_sample):
        commands.append(("pytest",))
    if "package.json" in manifest_names:
        commands.append(("npm", "test"))
    return [command for command in commands if command[0] in ExecutionRoot.ALLOWED_COMMANDS]


def _language_summary(files_sample: tuple[str, ...]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for file_path in files_sample:
        language = LANGUAGE_EXTENSIONS.get(Path(file_path).suffix.lower())
        if language is None:
            continue
        summary[language] = summary.get(language, 0) + 1
    return dict(sorted(summary.items()))


def _iter_repo_files(repo_root: Path) -> list[Path]:
    return [path for path in _iter_repo_paths(repo_root) if path.is_file()]


def _iter_repo_paths(repo_root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in repo_root.rglob("*")
            if not _path_has_skipped_part(path.relative_to(repo_root))
        ),
        key=lambda path: path.relative_to(repo_root).as_posix(),
    )


def _path_has_skipped_part(relative_path: Path) -> bool:
    return any(part in SKIPPED_REPO_DIRS for part in relative_path.parts)


def _last_result_succeeded(results: Sequence[dict[str, Any]]) -> bool:
    return bool(results and results[-1].get("success") and results[-1].get("verified"))


def _result_retryable(result: dict[str, Any]) -> bool:
    combined = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
    return "timeout" in combined or "temporar" in combined
