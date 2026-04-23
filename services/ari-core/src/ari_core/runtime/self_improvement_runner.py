from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence
from uuid import uuid4

from ..core.paths import DB_PATH, PROJECT_ROOT
from ..modules.coordination.db import list_coordination_entities, put_coordination_entity
from .action_plans import ActionPlan, build_action_plan
from .codex_adapter import CodexAdapter
from .loop_runner import LoopRunnerResult, run_goal_loop
from .repo_inspector import RepoInspectionResult, inspect_repo_state
from .response_contract import build_cli_response, render_cli_response
from .verification_profiles import (
    VerificationProfile,
    VerificationResult,
    VerificationContext,
    evaluate_profile,
    verification_profile_for_slice,
)


LoopRunCallable = Callable[..., LoopRunnerResult]


@dataclass(frozen=True, slots=True)
class ImprovementSlice:
    key: str
    title: str
    prompt_hint: str
    milestone: str = "general"
    priority: int = 50
    route_keywords: tuple[str, ...] = ()
    expected_paths: tuple[str, ...] = ()
    expected_symbols: dict[str, tuple[str, ...]] = field(default_factory=dict)
    verification_commands: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class SliceSelection:
    slice_spec: ImprovementSlice
    reason: str
    score: int
    evidence: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "sliceKey": self.slice_spec.key,
            "sliceTitle": self.slice_spec.title,
            "milestone": self.slice_spec.milestone,
            "reason": self.reason,
            "score": self.score,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class ControllerDecisionRecord:
    record_id: str
    loop_id: str
    cycle_index: int
    selected_slice_key: str
    selected_slice_title: str
    selected_slice_milestone: str
    selection_reason: str
    evidence: dict[str, object]
    verification_plan: list[str]
    outcome_status: str
    outcome_reason: str
    next_control_action: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.record_id,
            "loopId": self.loop_id,
            "cycleIndex": self.cycle_index,
            "selectedSliceKey": self.selected_slice_key,
            "selectedSliceTitle": self.selected_slice_title,
            "selectedSliceMilestone": self.selected_slice_milestone,
            "selectionReason": self.selection_reason,
            "evidence": self.evidence,
            "verificationPlan": self.verification_plan,
            "outcomeStatus": self.outcome_status,
            "outcomeReason": self.outcome_reason,
            "nextControlAction": self.next_control_action,
        }


@dataclass(frozen=True, slots=True)
class SelfImprovementCycle:
    slice_key: str
    loop_status: str
    verification_status: str
    reason: str
    action_plan: ActionPlan
    repo_inspection: RepoInspectionResult
    verification_result: VerificationResult
    worker_loop: LoopRunnerResult
    controller_decision: ControllerDecisionRecord

    def to_dict(self) -> dict[str, object]:
        return {
            "sliceKey": self.slice_key,
            "loopStatus": self.loop_status,
            "verificationStatus": self.verification_status,
            "reason": self.reason,
            "actionPlan": self.action_plan.to_dict(),
            "repoInspection": self.repo_inspection.to_dict(),
            "verificationResult": self.verification_result.to_dict(),
            "workerLoop": self.worker_loop.to_dict(),
            "controllerDecision": self.controller_decision.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SelfImprovementRunResult:
    goal: str
    status: str
    reason: str
    cycles_run: int
    cycles: list[SelfImprovementCycle]

    def to_dict(self) -> dict[str, object]:
        return {
            "goal": self.goal,
            "status": self.status,
            "reason": self.reason,
            "cyclesRun": self.cycles_run,
            "cycles": [cycle.to_dict() for cycle in self.cycles],
        }


DEFAULT_SLICE_CATALOG: tuple[ImprovementSlice, ...] = (
    ImprovementSlice(
        key="governed-coding-loop-quality",
        title="Strengthen governed coding loop quality",
        prompt_hint="Improve controller-quality slice selection, stronger verification, and explainable loop control without widening safety boundaries.",
        milestone="governed coding loop",
        priority=120,
        route_keywords=("governed coding loop", "controller", "verification", "self-improvement", "codex worker"),
        expected_paths=(
            "services/ari-core/src/ari_core/runtime/self_improvement_runner.py",
            "services/ari-core/src/ari_core/runtime/repo_inspector.py",
            "tests/unit/test_runtime_self_improvement_runner.py",
        ),
        expected_symbols={
            "services/ari-core/src/ari_core/runtime/self_improvement_runner.py": (
                "ControllerDecisionRecord",
                "_choose_next_slice",
                "_evaluate_slice_result",
            ),
            "services/ari-core/src/ari_core/runtime/repo_inspector.py": (
                "verification_runs",
                "verification_passed",
            ),
        },
        verification_commands=(
            (
                "./.venv312/bin/python",
                "-m",
                "pytest",
                "tests/unit/test_runtime_repo_inspector.py",
                "tests/unit/test_runtime_self_improvement_runner.py",
                "tests/unit/test_runtime_loop_runner.py",
                "-q",
            ),
        ),
    ),
    ImprovementSlice(
        key="governed-controller-trace",
        title="Persist richer controller trace",
        prompt_hint="Persist a typed controller decision trail that explains why each self-improvement cycle chose, retried, escalated, or stopped.",
        milestone="controller trace",
        priority=105,
        route_keywords=("trace", "persist", "decision trail", "controller record"),
        expected_paths=(
            "services/ari-core/src/ari_core/runtime/self_improvement_runner.py",
            "services/ari-core/src/ari_core/modules/coordination/db.py",
            "config/schema.sql",
        ),
        expected_symbols={
            "services/ari-core/src/ari_core/runtime/self_improvement_runner.py": ("ControllerDecisionRecord", "_persist_controller_decision"),
            "services/ari-core/src/ari_core/modules/coordination/db.py": ("runtime_controller_decision",),
            "config/schema.sql": ("ari_runtime_controller_decisions",),
        },
        verification_commands=(
            (
                "./.venv312/bin/python",
                "-m",
                "pytest",
                "tests/unit/test_runtime_self_improvement_runner.py",
                "-q",
            ),
        ),
    ),
    ImprovementSlice(
        key="runtime-loop-hardening",
        title="Harden the Codex worker loop",
        prompt_hint="Tighten the bounded runtime loop with better evaluation and trajectory evidence without broadening execution permissions.",
        milestone="runtime hardening",
        priority=85,
        route_keywords=("runtime", "worker loop", "codex loop", "retry", "escalate"),
        expected_paths=(
            "services/ari-core/src/ari_core/runtime/loop_runner.py",
            "tests/unit/test_runtime_loop_runner.py",
        ),
        expected_symbols={
            "services/ari-core/src/ari_core/runtime/loop_runner.py": ("_evaluate_worker_result",),
        },
        verification_commands=(
            (
                "./.venv312/bin/python",
                "-m",
                "pytest",
                "tests/unit/test_runtime_loop_runner.py",
                "-q",
            ),
        ),
    ),
)


class SelfImprovementRunner:
    def __init__(
        self,
        *,
        adapter: CodexAdapter | None = None,
        db_path: Path = DB_PATH,
        loop_run_callable: LoopRunCallable = run_goal_loop,
        slice_catalog: Sequence[ImprovementSlice] = DEFAULT_SLICE_CATALOG,
    ) -> None:
        self.adapter = adapter
        self.db_path = db_path
        self.loop_run_callable = loop_run_callable
        self.slice_catalog = tuple(slice_catalog)

    def run(
        self,
        goal: str,
        *,
        max_cycles: int = 2,
        cwd: Path | str | None = None,
    ) -> SelfImprovementRunResult:
        if not goal.strip():
            raise ValueError("goal is required")
        if max_cycles < 1:
            raise ValueError("max_cycles must be at least 1")

        repo_root = Path(cwd or PROJECT_ROOT).expanduser().resolve()
        cycles: list[SelfImprovementCycle] = []
        loop_id = f"self-improvement-run-{uuid4()}"
        previous_loops = self._load_previous_loops()
        controller_history = self._load_previous_controller_decisions()
        execution_intent = _load_execution_intent(repo_root)
        retry_selection: SliceSelection | None = None
        retry_cycle_context: SelfImprovementCycle | None = None

        for cycle_index in range(1, max_cycles + 1):
            pre_inspection = inspect_repo_state(repo_root)
            selection = retry_selection or self._choose_next_slice(
                goal,
                pre_inspection,
                previous_loops,
                controller_history,
                execution_intent,
            )
            previous_cycle = retry_cycle_context if retry_selection is not None else None
            retry_selection = None
            retry_cycle_context = None
            if selection is None:
                return SelfImprovementRunResult(
                    goal=goal,
                    status="stop",
                    reason="No further bounded self-improvement slice is available.",
                    cycles_run=len(cycles),
                    cycles=cycles,
                )

            verification_profile = verification_profile_for_slice(selection.slice_spec)
            action_plan = build_action_plan(
                goal=goal,
                selection=selection,
                verification_profile=verification_profile,
                previous_cycle=previous_cycle,
            )
            self._persist_action_plan(
                loop_id=loop_id,
                cycle_index=cycle_index,
                action_plan=action_plan,
            )
            worker_goal = self._build_worker_goal_reference(goal, selection.slice_spec)
            loop_result = self.loop_run_callable(
                worker_goal,
                max_cycles=1,
                cwd=repo_root,
                db_path=self.db_path,
                adapter=self.adapter,
                prepared_prompt=action_plan.prompt_text,
            )
            worker_run = loop_result.worker_runs[-1] if loop_result.worker_runs else None
            post_inspection = inspect_repo_state(
                repo_root,
                expected_paths=selection.slice_spec.expected_paths,
                expected_symbols=selection.slice_spec.expected_symbols,
                changed_paths_baseline=pre_inspection.changed_paths,
                worker_stdout="" if worker_run is None else worker_run.stdout,
                worker_stderr="" if worker_run is None else worker_run.stderr,
                worker_exit_code=None if worker_run is None else worker_run.exit_code,
            )
            verification_result = evaluate_profile(
                verification_profile,
                VerificationContext(
                    repo_root=repo_root,
                    pre_inspection=pre_inspection,
                    post_inspection=post_inspection,
                    worker_stdout="" if worker_run is None else worker_run.stdout,
                    worker_stderr="" if worker_run is None else worker_run.stderr,
                    worker_exit_code=None if worker_run is None else worker_run.exit_code,
                ),
            )
            verification_status, reason, next_control_action = _evaluate_slice_result(
                selection.slice_spec,
                loop_result,
                verification_result,
                retry_count=_retry_count_for_slice(selection.slice_spec.key, controller_history)
                + sum(
                    1
                    for cycle in cycles
                    if cycle.slice_key == selection.slice_spec.key and cycle.verification_status == "retry"
                ),
            )
            controller_decision = self._persist_controller_decision(
                loop_id=loop_id,
                cycle_index=cycle_index,
                goal=goal,
                selection=selection,
                action_plan=action_plan,
                inspection=post_inspection,
                verification_profile=verification_profile,
                verification_result=verification_result,
                outcome_status=verification_status,
                outcome_reason=reason,
                next_control_action=next_control_action,
            )
            cycle = SelfImprovementCycle(
                slice_key=selection.slice_spec.key,
                loop_status=loop_result.status,
                verification_status=verification_status,
                reason=reason,
                action_plan=action_plan,
                repo_inspection=post_inspection,
                verification_result=verification_result,
                worker_loop=loop_result,
                controller_decision=controller_decision,
            )
            cycles.append(cycle)
            controller_history.append(controller_decision.to_dict())
            previous_loops.append(
                {
                    "goal": worker_goal,
                    "status": loop_result.status,
                }
            )

            if next_control_action == "continue":
                continue
            if next_control_action == "retry":
                retry_selection = selection
                retry_cycle_context = cycle
                continue
            return SelfImprovementRunResult(
                goal=goal,
                status=verification_status,
                reason=reason,
                cycles_run=len(cycles),
                cycles=cycles,
            )

        return SelfImprovementRunResult(
            goal=goal,
            status="stop",
            reason="Reached the bounded cycle limit for this self-improvement run.",
            cycles_run=len(cycles),
            cycles=cycles,
        )

    def _load_previous_loops(self) -> list[dict[str, object]]:
        rows = list_coordination_entities("runtime_loop_record", limit=100, db_path=self.db_path)
        return [{key: row[key] for key in row.keys()} for row in rows]

    def _load_previous_controller_decisions(self) -> list[dict[str, object]]:
        rows = list_coordination_entities("runtime_controller_decision", limit=100, db_path=self.db_path)
        return [{key: row[key] for key in row.keys()} for row in rows]

    def _choose_next_slice(
        self,
        goal: str,
        inspection: RepoInspectionResult,
        previous_loops: Sequence[dict[str, object]],
        controller_history: Sequence[dict[str, object]],
        execution_intent: str,
    ) -> SliceSelection | None:
        completed_keys = {
            _slice_key_from_goal(str(row.get("goal", "")))
            for row in previous_loops
            if str(row.get("status", "")) == "stop"
        }
        escalated_keys = {
            str(row.get("selected_slice_key", ""))
            for row in controller_history
            if str(row.get("outcome_status", "")) == "escalate"
        }
        candidates: list[SliceSelection] = []

        for slice_spec in self.slice_catalog:
            if slice_spec.key in completed_keys:
                continue
            if slice_spec.key in escalated_keys:
                continue

            selection = _score_slice(
                slice_spec,
                goal=goal,
                execution_intent=execution_intent,
                inspection=inspection,
            )
            candidates.append(selection)

        if not candidates:
            return None
        return max(candidates, key=lambda item: item.score)

    def _persist_controller_decision(
        self,
        *,
        loop_id: str,
        cycle_index: int,
        goal: str,
        selection: SliceSelection,
        action_plan: ActionPlan,
        inspection: RepoInspectionResult,
        verification_profile: VerificationProfile,
        verification_result: VerificationResult,
        outcome_status: str,
        outcome_reason: str,
        next_control_action: str,
    ) -> ControllerDecisionRecord:
        record_id = f"runtime-controller-decision-{uuid4()}"
        payload = {
            "id": record_id,
            "loop_id": loop_id,
            "cycle_index": cycle_index,
            "goal": goal,
            "selected_slice_key": selection.slice_spec.key,
            "selected_slice_title": selection.slice_spec.title,
            "selected_slice_milestone": selection.slice_spec.milestone,
            "selection_reason": selection.reason,
            "evidence_json": json.dumps(
                {
                    "selection": selection.evidence,
                    "actionPlan": action_plan.to_dict(),
                    "inspection": inspection.to_dict(),
                    "verificationProfile": verification_profile.to_dict(),
                    "verification": verification_result.to_dict(),
                }
            ),
            "verification_plan_json": json.dumps(verification_profile.to_dict()),
            "outcome_status": outcome_status,
            "outcome_reason": outcome_reason,
            "next_control_action": next_control_action,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        put_coordination_entity("runtime_controller_decision", payload, db_path=self.db_path)
        return ControllerDecisionRecord(
            record_id=record_id,
            loop_id=loop_id,
            cycle_index=cycle_index,
            selected_slice_key=selection.slice_spec.key,
            selected_slice_title=selection.slice_spec.title,
            selected_slice_milestone=selection.slice_spec.milestone,
            selection_reason=selection.reason,
            evidence={
                "selection": selection.evidence,
                "actionPlan": action_plan.to_dict(),
                "inspection": inspection.to_dict(),
                "verificationProfile": verification_profile.to_dict(),
                "verification": verification_result.to_dict(),
            },
            verification_plan=list(verification_profile.to_dict()["checks"]),
            outcome_status=outcome_status,
            outcome_reason=outcome_reason,
            next_control_action=next_control_action,
        )

    def _persist_action_plan(
        self,
        *,
        loop_id: str,
        cycle_index: int,
        action_plan: ActionPlan,
    ) -> None:
        put_coordination_entity(
            "runtime_action_plan",
            {
                "id": f"runtime-action-plan-{uuid4()}",
                "loop_id": loop_id,
                "cycle_index": cycle_index,
                "slice_key": action_plan.slice_key,
                "milestone": action_plan.milestone,
                "attempt_kind": action_plan.attempt_kind,
                "task_description": action_plan.task_description,
                "constraints_json": json.dumps(action_plan.constraints),
                "likely_files_json": json.dumps(action_plan.likely_files),
                "expected_symbols_json": json.dumps(action_plan.expected_symbols),
                "verification_expectations_json": json.dumps(action_plan.verification_expectations),
                "retry_refinement_hints_json": json.dumps(action_plan.retry_refinement_hints),
                "failed_checks_json": json.dumps(action_plan.failed_checks),
                "prompt_text": action_plan.prompt_text,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            },
            db_path=self.db_path,
        )

    def _build_worker_goal_reference(self, goal: str, slice_spec: ImprovementSlice) -> str:
        return (
            f"[self-improvement:{slice_spec.key}] {goal}\n"
            f"Bounded milestone: {slice_spec.milestone}\n"
            f"Bounded slice: {slice_spec.title}"
        )


def run_self_improvement_loop(
    goal: str,
    *,
    max_cycles: int = 2,
    cwd: Path | str | None = None,
    db_path: Path = DB_PATH,
    adapter: CodexAdapter | None = None,
    slice_catalog: Sequence[ImprovementSlice] | None = None,
) -> SelfImprovementRunResult:
    runner = SelfImprovementRunner(
        adapter=adapter,
        db_path=db_path,
        slice_catalog=slice_catalog or DEFAULT_SLICE_CATALOG,
    )
    return runner.run(goal, max_cycles=max_cycles, cwd=cwd)


def handle_runtime_self_improve(args, db_path: Path = DB_PATH) -> int:
    result = run_self_improvement_loop(
        args.goal,
        max_cycles=args.max_cycles,
        cwd=args.cwd,
        db_path=db_path,
    )
    response = build_cli_response(
        goal=args.goal,
        route="self_improve",
        route_reason="The request explicitly invoked the bounded self-improvement runner.",
        result=result.to_dict(),
    )
    print(render_cli_response(response))
    return 0


def _evaluate_slice_result(
    slice_spec: ImprovementSlice,
    loop_result: LoopRunnerResult,
    verification_result: VerificationResult,
    *,
    retry_count: int,
) -> tuple[str, str, str]:
    if loop_result.status == "retry":
        return "retry", loop_result.reason, "retry"
    if loop_result.status == "escalate":
        return "escalate", loop_result.reason, "escalate"

    if verification_result.classification == "success" and slice_spec.expected_paths:
        return "continue", "The bounded slice produced strong repo and verification evidence.", "continue"
    if verification_result.classification == "success" and loop_result.worker_runs:
        worker_run = loop_result.worker_runs[-1]
        if worker_run.success and worker_run.stdout.strip():
            return "stop", "The bounded slice completed with a usable worker result and verification evidence.", "stop"

    failures = [check.details for check in verification_result.failed_checks]
    if verification_result.classification == "partial_success" and retry_count < 1:
        return "retry", "; ".join(failures), "retry"
    if retry_count < 1:
        return "retry", "; ".join(failures), "retry"
    return "escalate", "; ".join(failures), "escalate"


def _score_slice(
    slice_spec: ImprovementSlice,
    *,
    goal: str,
    execution_intent: str,
    inspection: RepoInspectionResult,
) -> SliceSelection:
    goal_text = goal.lower()
    intent_text = execution_intent.lower()
    score = slice_spec.priority
    reasons = [f"base priority {slice_spec.priority}"]
    evidence: dict[str, object] = {
        "goal": goal,
        "milestone": slice_spec.milestone,
    }

    keyword_hits = sum(1 for keyword in slice_spec.route_keywords if keyword.lower() in goal_text)
    if keyword_hits:
        score += keyword_hits * 20
        reasons.append(f"{keyword_hits} goal keyword hit(s)")

    milestone_hits = sum(1 for token in _tokenize_text(slice_spec.milestone) if token in goal_text or token in intent_text)
    if milestone_hits:
        score += milestone_hits * 15
        reasons.append(f"{milestone_hits} milestone token hit(s) from goal or execution intent")

    missing_paths = [path for path in slice_spec.expected_paths if not (Path(inspection.repo_root) / path).exists()]
    if missing_paths:
        score += min(30, len(missing_paths) * 10)
        reasons.append(f"{len(missing_paths)} expected path(s) are still missing")

    missing_symbols = {
        path: [symbol for symbol, matched in inspect_repo_state(inspection.repo_root, expected_symbols={path: symbols}).symbol_matches[path].items() if not matched]
        for path, symbols in slice_spec.expected_symbols.items()
    }
    missing_symbol_count = sum(len(symbols) for symbols in missing_symbols.values())
    if missing_symbol_count:
        score += min(25, missing_symbol_count * 5)
        reasons.append(f"{missing_symbol_count} expected symbol(s) are still missing")

    if slice_spec.verification_commands:
        score += 5
        reasons.append("slice includes explicit verification commands")

    evidence["missingPaths"] = missing_paths
    evidence["missingSymbols"] = {path: symbols for path, symbols in missing_symbols.items() if symbols}
    evidence["diffSummary"] = inspection.diff_summary
    reason = f"{slice_spec.title}: " + ", ".join(reasons)
    return SliceSelection(slice_spec=slice_spec, reason=reason, score=score, evidence=evidence)


def _load_execution_intent(repo_root: Path) -> str:
    execution_intent_path = repo_root / "EXECUTION_INTENT.md"
    if not execution_intent_path.exists():
        return ""
    return execution_intent_path.read_text(encoding="utf-8")


def _retry_count_for_slice(slice_key: str, controller_history: Sequence[dict[str, object]]) -> int:
    return sum(
        1
        for row in controller_history
        if str(row.get("selected_slice_key", "")) == slice_key and str(row.get("outcome_status", "")) == "retry"
    )


def _tokenize_text(text: str) -> set[str]:
    return {token for token in "".join(character if character.isalnum() else " " for character in text.lower()).split() if len(token) > 2}


def _slice_key_from_goal(goal: str) -> str | None:
    prefix = "[self-improvement:"
    if not goal.startswith(prefix):
        return None
    tail = goal[len(prefix):]
    if "]" not in tail:
        return None
    return tail.split("]", 1)[0].strip() or None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
