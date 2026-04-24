from __future__ import annotations

import json
import shlex
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from .models import (
    ExecutionGoal,
    FailureContext,
    PlannerResult,
    RepoContext,
    VerificationExpectation,
    WorkerAction,
    WorkerPlan,
)
from .sandbox import ExecutionRoot
from .tools import get_execution_tool_registry

MAX_PLAN_ACTIONS = 5
MODEL_CONFIDENCE_THRESHOLD = 0.70


@dataclass(frozen=True, slots=True)
class PlannerSelection:
    requested: str
    selected: str
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ExecutionPlanner(Protocol):
    planner_name: str

    def plan(
        self,
        goal: ExecutionGoal,
        repo_context: RepoContext,
        failure_context: FailureContext | None = None,
        memory_context: dict[str, object] | None = None,
    ) -> PlannerResult: ...


def resolve_execution_planner(
    *,
    planner: ExecutionPlanner | None = None,
    planner_mode: str | None = None,
    completion_fn: Callable[[dict[str, object]], str] | None = None,
) -> tuple[ExecutionPlanner, PlannerSelection]:
    if planner is not None:
        planner_name = getattr(planner, "planner_name", planner.__class__.__name__)
        return planner, PlannerSelection(
            requested="injected",
            selected=str(planner_name),
        )

    requested = (planner_mode or "rule_based").strip() or "rule_based"
    if requested == "rule_based":
        return RuleBasedPlanner(), PlannerSelection(
            requested=requested,
            selected=RuleBasedPlanner.planner_name,
        )

    if requested == "model":
        if completion_fn is not None:
            return ModelPlanner(completion_fn), PlannerSelection(
                requested=requested,
                selected=ModelPlanner.planner_name,
            )
        return RuleBasedPlanner(), PlannerSelection(
            requested=requested,
            selected=RuleBasedPlanner.planner_name,
            fallback_reason=(
                "Model planner requested but no completion function is configured; "
                "fell back to rule_based."
            ),
        )

    return RuleBasedPlanner(), PlannerSelection(
        requested=requested,
        selected=RuleBasedPlanner.planner_name,
        fallback_reason=(f"Unknown execution planner mode '{requested}'; fell back to rule_based."),
    )


class RuleBasedPlanner:
    planner_name = "rule_based"

    def plan(
        self,
        goal: ExecutionGoal,
        repo_context: RepoContext,
        failure_context: FailureContext | None = None,
        memory_context: dict[str, object] | None = None,
    ) -> PlannerResult:
        del failure_context, memory_context
        objective = goal.objective.strip()
        normalized = objective.lower()
        if not objective:
            return _reject(self.planner_name, "Execution goals require a non-empty objective.", 1.0)

        if normalized.startswith("write files "):
            plan = _parse_write_files_goal(objective)
            if plan is None:
                return _reject(
                    self.planner_name,
                    (
                        "Multi-file write goals must use: write files <path> "
                        "with <content>; <path> with <content>."
                    ),
                    0.9,
                )
            return PlannerResult(
                status="act",
                reason="The goal names a bounded multi-file write plan.",
                confidence=0.8,
                planner_name=self.planner_name,
                plan=plan,
            )

        if normalized.startswith("write file "):
            action = _parse_write_file_goal(objective)
            if action is None:
                return _reject(
                    self.planner_name,
                    "Write goals must use: write file <path> with <content>.",
                    0.9,
                )
            return PlannerResult(
                status="act",
                reason="The goal names a bounded file write with explicit target path and content.",
                confidence=0.82,
                planner_name=self.planner_name,
                plan=_single_action_plan(
                    action,
                    reason="Write the requested file and verify its final content.",
                ),
            )

        if normalized.startswith("read file "):
            path = objective[len("read file ") :].strip()
            action = WorkerAction(
                action_type="read_file",
                payload={"path": path},
                reason="Read the requested path inside the execution root.",
            )
            return PlannerResult(
                status="act",
                reason="The goal requests a bounded file read.",
                confidence=0.86,
                planner_name=self.planner_name,
                plan=_single_action_plan(action, reason="Read the requested file."),
            )

        if normalized.startswith("run "):
            raw_command = objective[len("run ") :].strip()
            try:
                command = shlex.split(raw_command)
            except ValueError as error:
                return _reject(self.planner_name, f"Command parsing failed: {error}", 0.93)
            action = WorkerAction(
                action_type="run_command",
                payload={"command": command},
                reason="Run the requested command if it passes sandbox validation.",
            )
            return PlannerResult(
                status="act",
                reason=(
                    "The goal requests a bounded command run; validation will enforce "
                    "the sandbox allowlist."
                ),
                confidence=0.76,
                planner_name=self.planner_name,
                plan=_single_action_plan(action, reason="Run the requested bounded command."),
            )

        if any(token in normalized for token in ("inspect", "status", "list", "context", "repo")):
            action = WorkerAction(
                action_type="run_command",
                payload={"command": ["ls"]},
                reason=f"List the execution root for repo context at {repo_context.repo_root}.",
            )
            return PlannerResult(
                status="act",
                reason=(
                    "The goal asks for repository context, so ARI will run the safest "
                    "read-only workspace action."
                ),
                confidence=0.79,
                planner_name=self.planner_name,
                plan=_single_action_plan(action, reason="Inspect the execution root."),
            )

        return _reject(
            self.planner_name,
            "No bounded execution action matched this goal yet.",
            0.72,
        )


class ModelPlanner:
    planner_name = "model"

    def __init__(
        self,
        completion_fn: Callable[[dict[str, object]], str],
        *,
        confidence_threshold: float = MODEL_CONFIDENCE_THRESHOLD,
        max_plan_actions: int = MAX_PLAN_ACTIONS,
    ) -> None:
        self.completion_fn = completion_fn
        self.confidence_threshold = confidence_threshold
        self.max_plan_actions = max_plan_actions
        self.last_prompt_payload: dict[str, object] | None = None

    def plan(
        self,
        goal: ExecutionGoal,
        repo_context: RepoContext,
        failure_context: FailureContext | None = None,
        memory_context: dict[str, object] | None = None,
    ) -> PlannerResult:
        payload = self._build_prompt_payload(
            goal,
            repo_context,
            failure_context,
            memory_context,
        )
        self.last_prompt_payload = payload
        try:
            raw_response = self.completion_fn(payload)
        except Exception as error:
            return _reject(
                self.planner_name,
                f"Planner completion failed: {error}",
                0.0,
                failure_context,
            )
        return self._parse_response(raw_response, repo_context, failure_context)

    def _build_prompt_payload(
        self,
        goal: ExecutionGoal,
        repo_context: RepoContext,
        failure_context: FailureContext | None,
        memory_context: dict[str, object] | None,
    ) -> dict[str, object]:
        return {
            "instruction": "Return only strict JSON for one bounded WorkerPlan.",
            "schema": {
                "confidence": "number between 0 and 1",
                "reason": "string",
                "actions": [
                    {
                        "type": "read_file | write_file | patch_file | run_command",
                        "path": "required for file actions and must be in allowed_files",
                        "content": "required for write_file",
                        "find": "required for patch_file",
                        "replace": "required for patch_file",
                        "command": "required list[str] for run_command",
                    }
                ],
                "verification": [
                    {
                        "type": "action_success | file_content | path_exists",
                        "target": "file path or action target",
                        "expected": "optional string",
                        "reason": "string",
                    }
                ],
            },
            "goal": goal.to_dict(),
            "repo_context": repo_context.to_dict(),
            "allowed_files": list(repo_context.files_sample),
            **get_execution_tool_registry().prompt_payload(),
            "max_plan_actions": self.max_plan_actions,
            "confidence_threshold": self.confidence_threshold,
            "failure_context": None if failure_context is None else failure_context.to_dict(),
            "memory_context": memory_context or {},
        }

    def _parse_response(
        self,
        raw_response: str,
        repo_context: RepoContext,
        failure_context: FailureContext | None,
    ) -> PlannerResult:
        try:
            decoded = json.loads(raw_response)
        except json.JSONDecodeError as error:
            return _reject(
                self.planner_name,
                f"Planner returned invalid JSON: {error}",
                0.0,
                failure_context,
            )
        if not isinstance(decoded, dict):
            return _reject(
                self.planner_name,
                "Planner JSON must be an object.",
                0.0,
                failure_context,
            )

        confidence = _coerce_confidence(decoded.get("confidence"))
        if confidence is None:
            return _reject(
                self.planner_name,
                "Planner JSON requires numeric confidence.",
                0.0,
                failure_context,
            )
        if confidence < self.confidence_threshold:
            return _reject(
                self.planner_name,
                (
                    f"Planner confidence {confidence:.2f} is below threshold "
                    f"{self.confidence_threshold:.2f}."
                ),
                confidence,
                failure_context,
            )

        reason = str(decoded.get("reason") or "Model planner proposed a bounded plan.")
        raw_actions = decoded.get("actions")
        if not isinstance(raw_actions, list) or not raw_actions:
            return _reject(
                self.planner_name,
                "Planner JSON requires a non-empty actions list.",
                confidence,
                failure_context,
            )
        if len(raw_actions) > self.max_plan_actions:
            return _reject(
                self.planner_name,
                f"Execution plans are bounded to {self.max_plan_actions} actions.",
                confidence,
                failure_context,
            )

        allowed_files = set(repo_context.files_sample)
        action_result = _parse_model_actions(raw_actions, allowed_files, repo_context)
        if isinstance(action_result, str):
            return _reject(self.planner_name, action_result, confidence, failure_context)

        verification_result = _parse_model_verification(
            decoded.get("verification"),
            allowed_files,
            action_result,
        )
        if isinstance(verification_result, str):
            return _reject(self.planner_name, verification_result, confidence, failure_context)

        return PlannerResult(
            status="act",
            reason=reason,
            confidence=confidence,
            planner_name=self.planner_name,
            plan=WorkerPlan(
                actions=tuple(action_result),
                verification=tuple(verification_result),
                reason=reason,
            ),
            failure_context=failure_context,
        )


def _reject(
    planner_name: str,
    reason: str,
    confidence: float,
    failure_context: FailureContext | None = None,
) -> PlannerResult:
    return PlannerResult(
        status="reject",
        reason=reason,
        confidence=confidence,
        planner_name=planner_name,
        failure_context=failure_context,
    )


def _parse_model_actions(
    raw_actions: list[object],
    allowed_files: set[str],
    repo_context: RepoContext,
) -> list[WorkerAction] | str:
    actions: list[WorkerAction] = []
    execution_root = ExecutionRoot(repo_context.repo_root)
    tool_registry = get_execution_tool_registry()
    for raw_action in raw_actions:
        if not isinstance(raw_action, dict):
            return "Each planner action must be an object."
        action_type = str(raw_action.get("type") or raw_action.get("action_type") or "")

        if action_type in {"read_file", "write_file", "patch_file"}:
            path = str(raw_action.get("path") or "")
            payload: dict[str, Any] = {"path": path}
            if action_type == "write_file":
                if "content" in raw_action:
                    payload["content"] = str(raw_action["content"])
            elif action_type == "patch_file":
                find_text = str(raw_action.get("find") or "")
                payload["find"] = find_text
                payload["replace"] = str(raw_action.get("replace") or "")
            validation_error = tool_registry.validate_execution_action(
                {"type": action_type, **payload},
                execution_root=execution_root,
                allowed_files=allowed_files,
            )
            if validation_error is not None:
                return validation_error
            actions.append(
                WorkerAction(
                    action_type=action_type,
                    payload=payload,
                    reason=str(raw_action.get("reason") or "Model-planned file action."),
                )
            )
            continue

        if action_type == "run_command":
            command = raw_action.get("command")
            action_payload = {"type": "run_command", "command": command}
            validation_error = tool_registry.validate_execution_action(
                action_payload,
                execution_root=execution_root,
                allowed_files=allowed_files,
            )
            if validation_error is not None:
                return validation_error
            checked_command = list(command) if isinstance(command, list) else []
            actions.append(
                WorkerAction(
                    action_type="run_command",
                    payload={"command": checked_command},
                    reason=str(raw_action.get("reason") or "Model-planned command action."),
                )
            )
            continue

        validation_error = tool_registry.validate_execution_action(
            {"type": action_type},
            execution_root=execution_root,
            allowed_files=allowed_files,
        )
        if validation_error is not None:
            return validation_error
        return f"Model planner parser does not support action type: {action_type}"
    return actions


def _parse_model_verification(
    raw_verification: object,
    allowed_files: set[str],
    actions: list[WorkerAction],
) -> list[VerificationExpectation] | str:
    if raw_verification is None:
        return _expectations_for_actions(actions)
    if not isinstance(raw_verification, list):
        return "Planner verification must be a list when provided."

    expectations: list[VerificationExpectation] = []
    for raw_expectation in raw_verification:
        if not isinstance(raw_expectation, dict):
            return "Each planner verification expectation must be an object."
        expectation_type = str(
            raw_expectation.get("type") or raw_expectation.get("expectation_type") or ""
        )
        if expectation_type not in {"action_success", "file_content", "path_exists"}:
            return f"Planner verification type is not allowed: {expectation_type or '<missing>'}"
        target = str(raw_expectation.get("target") or "")
        if expectation_type in {"file_content", "path_exists"} and target not in allowed_files:
            return (
                "Planner verification referenced a file outside RepoContext: "
                f"{target or '<missing>'}"
            )
        expectations.append(
            VerificationExpectation(
                expectation_type=expectation_type,
                target=target,
                expected=(
                    None
                    if raw_expectation.get("expected") is None
                    else str(raw_expectation["expected"])
                ),
                reason=str(raw_expectation.get("reason") or "Model-planned verification."),
            )
        )
    return expectations


def _parse_write_file_goal(objective: str) -> WorkerAction | None:
    remainder = objective[len("write file ") :].strip()
    if " with " not in remainder:
        return None
    path, content = remainder.split(" with ", 1)
    path = path.strip()
    if not path:
        return None
    return WorkerAction(
        action_type="write_file",
        payload={"path": path, "content": content},
        reason="Write explicit goal content to an explicit path inside the execution root.",
    )


def _parse_write_files_goal(objective: str) -> WorkerPlan | None:
    remainder = objective[len("write files ") :].strip()
    if not remainder:
        return None

    actions: list[WorkerAction] = []
    for segment in remainder.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        action = _parse_write_file_goal(f"write file {segment}")
        if action is None:
            return None
        actions.append(action)

    if not actions:
        return None
    return WorkerPlan(
        actions=tuple(actions),
        verification=tuple(_expectations_for_actions(actions)),
        reason="Execute the explicit multi-file write plan and verify every target.",
    )


def _single_action_plan(action: WorkerAction, *, reason: str) -> WorkerPlan:
    return WorkerPlan(
        actions=(action,),
        verification=tuple(_expectations_for_actions([action])),
        reason=reason,
    )


def _expectations_for_actions(actions: list[WorkerAction]) -> list[VerificationExpectation]:
    expectations: list[VerificationExpectation] = []
    for action in actions:
        if action.action_type == "write_file":
            expectations.append(
                VerificationExpectation(
                    expectation_type="file_content",
                    target=str(action.payload["path"]),
                    expected=str(action.payload["content"]),
                    reason="Verify the file contains the exact planned content.",
                )
            )
        elif action.action_type == "patch_file":
            expectations.append(
                VerificationExpectation(
                    expectation_type="path_exists",
                    target=str(action.payload["path"]),
                    reason="Patch actions are verified by action-level replacement checks.",
                )
            )
        else:
            expectations.append(
                VerificationExpectation(
                    expectation_type="action_success",
                    target=action.action_type,
                    reason="The action-level result is the verification signal.",
                )
            )
    return expectations


def _coerce_confidence(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if confidence < 0 or confidence > 1:
        return None
    return confidence
