from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Sequence

from ..core.paths import PROJECT_ROOT
from ..modules.notes.db import save_ari_note
from .codex_adapter import CodexAdapter
from .loop_runner import run_goal_loop
from .playground import PlaygroundWorkspace, persist_playground_summary, prepare_playground_workspace
from .repo_inspector import inspect_repo_state
from .request_router import classify_request
from .response_contract import AriCliResponse, build_cli_response
from .self_improvement_runner import ImprovementSlice, run_self_improvement_loop


AcceptanceStatus = Literal["pass", "partial", "fail"]


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    name: str
    goal: str
    expected_route: str
    description: str
    minimum_evidence: list[str]


@dataclass(frozen=True, slots=True)
class AcceptanceResult:
    status: AcceptanceStatus
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ScenarioRunResult:
    scenario: str
    goal: str
    route: str
    acceptance: AcceptanceResult
    response: dict[str, object]
    selected_slice: str | None
    action_plan: dict[str, object] | None
    worker_result: dict[str, object] | None
    semantic_verification: dict[str, object] | None
    controller_decision: dict[str, object] | None
    changed_files: list[str]
    summary_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["acceptance"] = self.acceptance.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class ScenarioHarnessResult:
    workspace: dict[str, object]
    scenarios: list[ScenarioRunResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "workspace": self.workspace,
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
        }


DEFAULT_SCENARIOS: tuple[ScenarioDefinition, ...] = (
    ScenarioDefinition(
        name="repo_inspect",
        goal="inspect repo status and what changed",
        expected_route="repo_inspect",
        description="Inspect the disposable workspace and return repo state.",
        minimum_evidence=["route matches", "git inspection available"],
    ),
    ScenarioDefinition(
        name="note_capture",
        goal="remember this playground architecture note for later",
        expected_route="document_or_note_capture",
        description="Capture a note through the outward ARI surface.",
        minimum_evidence=["route matches", "note id present"],
    ),
    ScenarioDefinition(
        name="plan_only",
        goal="plan the next safe ARI playground step",
        expected_route="plan_only",
        description="Return a bounded plan without execution.",
        minimum_evidence=["route matches", "planned status"],
    ),
    ScenarioDefinition(
        name="codex_loop",
        goal="implement a tiny bounded coding worker change in the playground",
        expected_route="codex_loop",
        description="Run a bounded Codex worker loop inside the playground.",
        minimum_evidence=["route matches", "worker success"],
    ),
    ScenarioDefinition(
        name="self_improve",
        goal="improve ARI's governed coding loop safely in the playground",
        expected_route="self_improve",
        description="Run a bounded self-improvement cycle with semantic verification.",
        minimum_evidence=["route matches", "controller decision present", "verification result present"],
    ),
)


def run_playground_goal(
    goal: str,
    *,
    workspace: Path | str | None = None,
    reset_workspace: bool = False,
    use_real_codex: bool = False,
) -> ScenarioRunResult:
    prepared = prepare_playground_workspace(workspace, reset=reset_workspace)
    scenario = ScenarioDefinition(
        name="playground_run",
        goal=goal,
        expected_route=classify_request(goal).route,
        description="Direct goal run inside a disposable playground workspace.",
        minimum_evidence=["route matches"],
    )
    result = _run_single_scenario(
        scenario,
        prepared,
        use_real_codex=use_real_codex,
        persist_name="playground-run",
    )
    return result


def run_runtime_scenarios(
    *,
    workspace: Path | str | None = None,
    scenario_names: Sequence[str] | None = None,
    reset_workspace: bool = False,
    use_real_codex: bool = False,
) -> ScenarioHarnessResult:
    selected = _select_scenarios(scenario_names)
    base_root = Path(workspace).expanduser().resolve() if workspace else (PROJECT_ROOT / "tmp" / "ari-scenarios").resolve()
    results = [
        _run_single_scenario(
            scenario,
            prepare_playground_workspace(_scenario_workspace(base_root, scenario.name), reset=reset_workspace),
            use_real_codex=use_real_codex,
            persist_name=f"scenario-{scenario.name}",
        )
        for scenario in selected
    ]
    workspace_summary = {
        "root": str(base_root),
        "mode": "scenario_harness",
        "isolatedScenarioWorkspaces": True,
    }
    return ScenarioHarnessResult(workspace=workspace_summary, scenarios=results)


def handle_runtime_smoke_test(args) -> int:
    scenario_names = None if args.scenario in {None, "all"} else [args.scenario]
    result = run_runtime_scenarios(
        workspace=args.workspace,
        scenario_names=scenario_names,
        reset_workspace=args.reset_workspace,
        use_real_codex=args.use_real_codex,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


def handle_runtime_playground_run(args) -> int:
    result = run_playground_goal(
        args.goal,
        workspace=args.workspace,
        reset_workspace=args.reset_workspace,
        use_real_codex=args.use_real_codex,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


def _select_scenarios(scenario_names: Sequence[str] | None) -> list[ScenarioDefinition]:
    if scenario_names is None:
        return list(DEFAULT_SCENARIOS)

    requested = set(scenario_names)
    known = {scenario.name for scenario in DEFAULT_SCENARIOS}
    unknown = sorted(requested - known)
    if unknown:
        raise ValueError(f"Unknown scenario name(s): {', '.join(unknown)}")
    return [scenario for scenario in DEFAULT_SCENARIOS if scenario.name in requested]


def _scenario_workspace(base_root: Path, scenario_name: str) -> Path:
    return base_root / scenario_name


def _run_single_scenario(
    scenario: ScenarioDefinition,
    workspace: PlaygroundWorkspace,
    *,
    use_real_codex: bool,
    persist_name: str,
) -> ScenarioRunResult:
    root = Path(workspace.root)
    db_path = Path(workspace.db_path)
    route = classify_request(scenario.goal).route
    response = _dispatch_goal(
        scenario.goal,
        route=route,
        workspace=workspace,
        db_path=db_path,
        use_real_codex=use_real_codex,
        scenario=scenario,
    )
    data = response.to_dict()
    response_data = data["data"]
    repo_snapshot = inspect_repo_state(root)
    result = ScenarioRunResult(
        scenario=scenario.name,
        goal=scenario.goal,
        route=str(data["route"]),
        acceptance=_assess_scenario(scenario, data),
        response=data,
        selected_slice=_extract_selected_slice(response_data),
        action_plan=_extract_action_plan(response_data),
        worker_result=_extract_worker_result(response_data),
        semantic_verification=_extract_verification_result(response_data),
        controller_decision=_extract_controller_decision(response_data),
        changed_files=repo_snapshot.changed_paths,
    )
    summary_path = persist_playground_summary(workspace, persist_name, result.to_dict())
    return ScenarioRunResult(
        scenario=result.scenario,
        goal=result.goal,
        route=result.route,
        acceptance=result.acceptance,
        response=result.response,
        selected_slice=result.selected_slice,
        action_plan=result.action_plan,
        worker_result=result.worker_result,
        semantic_verification=result.semantic_verification,
        controller_decision=result.controller_decision,
        changed_files=result.changed_files,
        summary_path=summary_path,
    )


def _dispatch_goal(
    goal: str,
    *,
    route: str,
    workspace: PlaygroundWorkspace,
    db_path: Path,
    use_real_codex: bool,
    scenario: ScenarioDefinition,
) -> AriCliResponse:
    root = Path(workspace.root)
    adapter = None
    if not use_real_codex:
        adapter = CodexAdapter(
            backend_mode="stub",
            command_prefix=workspace.worker_command_prefix,
        )

    if route == "repo_inspect":
        result = inspect_repo_state(root).to_dict()
        return build_cli_response(goal=goal, route=route, route_reason="Scenario harness repo inspection.", result=result)

    if route == "document_or_note_capture":
        note = save_ari_note("Playground note", goal, db_path=db_path)
        result = {
            "id": int(note["id"]),
            "title": note["title"],
            "body": note["body"],
            "created_at": note["created_at"],
        }
        return build_cli_response(goal=goal, route=route, route_reason="Scenario harness note capture.", result=result)

    if route == "plan_only":
        result = {
            "status": "planned",
            "goal": goal,
            "next_step": "Review the bounded plan before choosing an execution route.",
        }
        return build_cli_response(goal=goal, route=route, route_reason="Scenario harness plan-only route.", result=result)

    if route == "codex_loop":
        result = run_goal_loop(
            goal,
            max_cycles=1,
            cwd=root,
            db_path=db_path,
            adapter=adapter,
        ).to_dict()
        return build_cli_response(goal=goal, route=route, route_reason="Scenario harness bounded Codex loop.", result=result)

    if route == "self_improve":
        slice_catalog = (
            ImprovementSlice(
                key="playground-self-improve",
                title="Strengthen the playground self-improvement loop",
                prompt_hint="Update the bounded playground module so semantic verification can confirm success cleanly.",
                milestone="playground self-improvement",
                priority=100,
                route_keywords=("playground", "governed coding loop", "self-improve"),
                expected_paths=("playground_module.py",),
                expected_symbols={"playground_module.py": ("PLAYGROUND_READY",)},
            ),
        )
        result = run_self_improvement_loop(
            goal,
            max_cycles=2,
            cwd=root,
            db_path=db_path,
            adapter=adapter,
            slice_catalog=slice_catalog,
        ).to_dict()
        return build_cli_response(goal=goal, route=route, route_reason="Scenario harness bounded self-improvement loop.", result=result)

    raise ValueError(f"Unsupported scenario route: {route}")


def _assess_scenario(scenario: ScenarioDefinition, payload: dict[str, object]) -> AcceptanceResult:
    route = str(payload.get("route", ""))
    if route != scenario.expected_route:
        return AcceptanceResult(status="fail", reason=f"Expected route {scenario.expected_route}, got {route}.")

    data = payload.get("data", {})
    if not isinstance(data, dict):
        return AcceptanceResult(status="fail", reason="Scenario response data was not a dict.")

    if scenario.name == "repo_inspect":
        if data.get("git_available") is True:
            return AcceptanceResult(status="pass", reason="Repo inspection returned git state.")
        return AcceptanceResult(status="partial", reason="Repo inspection returned a route but no git evidence.")

    if scenario.name == "note_capture":
        if data.get("id"):
            return AcceptanceResult(status="pass", reason="Note capture returned a canonical note id.")
        return AcceptanceResult(status="partial", reason="Note capture routed correctly but did not return a note id.")

    if scenario.name == "plan_only":
        if payload.get("status") == "planned":
            return AcceptanceResult(status="pass", reason="Plan-only scenario returned the planned contract.")
        return AcceptanceResult(status="partial", reason="Plan-only route succeeded but did not return planned status.")

    if scenario.name == "codex_loop":
        worker_runs = data.get("workerRuns", [])
        if worker_runs and worker_runs[-1].get("success") is True:
            return AcceptanceResult(status="pass", reason="Codex loop produced a successful worker run.")
        if payload.get("status") == "attention_needed":
            return AcceptanceResult(status="partial", reason="Codex loop reached the route but not a successful worker run.")
        return AcceptanceResult(status="fail", reason="Codex loop did not produce usable worker evidence.")

    if scenario.name == "self_improve":
        cycles = data.get("cycles", [])
        if cycles and cycles[-1].get("controllerDecision") and cycles[-1].get("verificationResult"):
            return AcceptanceResult(status="pass", reason="Self-improvement scenario produced controller and verification evidence.")
        if cycles:
            return AcceptanceResult(status="partial", reason="Self-improvement route ran but missing controller or verification detail.")
        return AcceptanceResult(status="fail", reason="Self-improvement route did not produce cycle evidence.")

    return AcceptanceResult(status="partial", reason="Scenario completed without a specialized acceptance rule.")


def _extract_selected_slice(data: dict[str, object]) -> str | None:
    cycles = data.get("cycles", [])
    if isinstance(cycles, list) and cycles:
        return cycles[-1].get("sliceKey")
    return None


def _extract_action_plan(data: dict[str, object]) -> dict[str, object] | None:
    cycles = data.get("cycles", [])
    if isinstance(cycles, list) and cycles:
        action_plan = cycles[-1].get("actionPlan")
        return action_plan if isinstance(action_plan, dict) else None
    return None


def _extract_worker_result(data: dict[str, object]) -> dict[str, object] | None:
    if isinstance(data.get("workerRuns"), list) and data["workerRuns"]:
        return data["workerRuns"][-1]
    cycles = data.get("cycles", [])
    if isinstance(cycles, list) and cycles:
        worker_loop = cycles[-1].get("workerLoop", {})
        worker_runs = worker_loop.get("workerRuns", []) if isinstance(worker_loop, dict) else []
        if worker_runs:
            return worker_runs[-1]
    return None


def _extract_verification_result(data: dict[str, object]) -> dict[str, object] | None:
    cycles = data.get("cycles", [])
    if isinstance(cycles, list) and cycles:
        verification = cycles[-1].get("verificationResult")
        return verification if isinstance(verification, dict) else None
    return None


def _extract_controller_decision(data: dict[str, object]) -> dict[str, object] | None:
    cycles = data.get("cycles", [])
    if isinstance(cycles, list) and cycles:
        controller = cycles[-1].get("controllerDecision")
        return controller if isinstance(controller, dict) else None
    return None
