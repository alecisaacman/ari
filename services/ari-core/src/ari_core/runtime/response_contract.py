from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal


ResponseStatus = Literal["completed", "in_progress", "attention_needed", "planned"]


@dataclass(frozen=True, slots=True)
class AriCliResponse:
    contract_version: str
    identity: str
    surface: str
    goal: str
    route: str
    route_reason: str
    status: ResponseStatus
    ok: bool
    summary: str
    next_step: str | None
    data: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["contractVersion"] = payload.pop("contract_version")
        payload["routeReason"] = payload.pop("route_reason")
        payload["nextStep"] = payload.pop("next_step")
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def build_cli_response(
    *,
    goal: str,
    route: str,
    route_reason: str,
    result: dict[str, object],
) -> AriCliResponse:
    status, summary, next_step = _describe_route_result(route, result)
    return AriCliResponse(
        contract_version="ari.cli.v1",
        identity="ARI",
        surface="terminal",
        goal=goal,
        route=route,
        route_reason=route_reason,
        status=status,
        ok=status != "attention_needed",
        summary=summary,
        next_step=next_step,
        data=result,
    )


def render_cli_response(response: AriCliResponse) -> str:
    return response.to_json()


def _describe_route_result(
    route: str,
    result: dict[str, object],
) -> tuple[ResponseStatus, str, str | None]:
    if route == "self_improve":
        return _describe_self_improvement_result(result)
    if route == "codex_loop":
        return _describe_codex_loop_result(result)
    if route == "repo_inspect":
        return _describe_repo_inspection_result(result)
    if route == "document_or_note_capture":
        title = str(result.get("title", "Captured note"))
        return (
            "completed",
            f"ARI captured the note '{title}'.",
            "Use the same outward `ari` entry whenever you want to capture or revisit more context.",
        )
    if route == "plan_only":
        return (
            "planned",
            "ARI produced a bounded plan without executing work.",
            str(result.get("next_step", "Review the plan and choose whether to run it through ARI.")),
        )

    return (
        "attention_needed",
        "ARI returned a result through an unknown route contract.",
        "Inspect the returned payload before continuing.",
    )


def _describe_self_improvement_result(result: dict[str, object]) -> tuple[ResponseStatus, str, str | None]:
    internal_status = str(result.get("status", ""))
    cycles_run = int(result.get("cyclesRun", 0) or 0)
    reason = str(result.get("reason", ""))

    if internal_status == "stop":
        return (
            "completed",
            f"ARI completed the bounded self-improvement run in {cycles_run} cycle(s).",
            None,
        )
    if internal_status in {"continue", "retry"}:
        return (
            "in_progress",
            f"ARI completed a bounded self-improvement slice and can continue from here. {reason}".strip(),
            "Review the last cycle evidence and continue only if the next slice stays inside the same safe boundary.",
        )
    return (
        "attention_needed",
        f"ARI stopped the self-improvement run because attention is needed. {reason}".strip(),
        "Inspect the latest cycle result and decide whether to refine the goal or intervene manually.",
    )


def _describe_codex_loop_result(result: dict[str, object]) -> tuple[ResponseStatus, str, str | None]:
    internal_status = str(result.get("status", ""))
    cycles_run = int(result.get("cyclesRun", 0) or 0)
    reason = str(result.get("reason", ""))

    if internal_status == "stop":
        return (
            "completed",
            f"ARI completed the bounded Codex worker loop in {cycles_run} cycle(s).",
            None,
        )
    if internal_status == "retry":
        return (
            "in_progress",
            f"ARI has another bounded worker pass available. {reason}".strip(),
            "Review the last worker output before allowing another bounded pass.",
        )
    return (
        "attention_needed",
        f"ARI could not finish the bounded Codex worker loop cleanly. {reason}".strip(),
        "Inspect the latest worker stderr and decide whether to refine the goal or escalate manually.",
    )


def _describe_repo_inspection_result(result: dict[str, object]) -> tuple[ResponseStatus, str, str | None]:
    changed_paths = list(result.get("changed_paths", result.get("changedPaths", [])) or [])
    git_dirty = bool(result.get("git_dirty", result.get("gitDirty", False)))
    if git_dirty:
        count = len(changed_paths)
        return (
            "attention_needed",
            f"ARI inspected the repo and found {count} changed path(s).",
            "Review the changed paths to decide whether ARI should plan, self-improve, or leave the repo as-is.",
        )
    return (
        "completed",
        "ARI inspected the repo and found a clean working tree.",
        None,
    )
