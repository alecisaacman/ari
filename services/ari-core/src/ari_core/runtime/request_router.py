from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from ..core.paths import DB_PATH, PROJECT_ROOT
from ..modules.notes.db import save_ari_note
from .loop_runner import run_goal_loop
from .repo_inspector import inspect_repo_state
from .response_contract import AriCliResponse, build_cli_response, render_cli_response
from .self_improvement_runner import run_self_improvement_loop


RouteName = Literal[
    "self_improve",
    "codex_loop",
    "repo_inspect",
    "document_or_note_capture",
    "plan_only",
]


@dataclass(frozen=True, slots=True)
class RouteDecision:
    route: RouteName
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RouteResult:
    route: RouteName
    reason: str
    result: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "route": self.route,
            "reason": self.reason,
            "result": self.result,
        }


def route_goal_request(
    goal: str,
    *,
    cwd: Path | str | None = None,
    db_path: Path = DB_PATH,
) -> AriCliResponse:
    routed = route_request(goal, cwd=cwd, db_path=db_path)
    return build_cli_response(
        goal=goal,
        route=routed.route,
        route_reason=routed.reason,
        result=routed.result,
    )


def classify_request(goal: str) -> RouteDecision:
    lowered = " ".join(goal.lower().split())

    if _contains_any(lowered, ("improve ari", "self-improve", "self improve", "autonomous coding loop", "improve the runtime", "improve the loop")):
        return RouteDecision(
            route="self_improve",
            reason="The request is explicitly about improving ARI itself.",
        )

    if _contains_any(lowered, ("inspect repo", "repo status", "git status", "what changed", "check repo", "inspect the repository", "repo inspect")):
        return RouteDecision(
            route="repo_inspect",
            reason="The request is explicitly about repository state inspection.",
        )

    if _contains_any(lowered, ("remember", "note this", "capture this", "save note", "document this", "write this down")):
        return RouteDecision(
            route="document_or_note_capture",
            reason="The request is best handled as note or documentation capture.",
        )

    if _contains_any(lowered, ("plan", "outline", "strategy", "what should we do", "what's next", "plan only")):
        return RouteDecision(
            route="plan_only",
            reason="The request is asking for planning rather than immediate execution.",
        )

    return RouteDecision(
        route="codex_loop",
        reason="Default route for implementation-oriented natural-language goals.",
    )


def route_request(
    goal: str,
    *,
    cwd: Path | str | None = None,
    db_path: Path = DB_PATH,
) -> RouteResult:
    if not goal.strip():
        raise ValueError("goal is required")

    decision = classify_request(goal)
    resolved_cwd = Path(cwd or PROJECT_ROOT).expanduser().resolve()

    if decision.route == "self_improve":
        result = run_self_improvement_loop(goal, cwd=resolved_cwd, db_path=db_path).to_dict()
        return RouteResult(route=decision.route, reason=decision.reason, result=result)

    if decision.route == "codex_loop":
        result = run_goal_loop(goal, cwd=resolved_cwd, db_path=db_path).to_dict()
        return RouteResult(route=decision.route, reason=decision.reason, result=result)

    if decision.route == "repo_inspect":
        result = inspect_repo_state(resolved_cwd).to_dict()
        return RouteResult(route=decision.route, reason=decision.reason, result=result)

    if decision.route == "document_or_note_capture":
        title = _note_title_from_goal(goal)
        note = save_ari_note(title, goal, db_path=db_path)
        result = {
            "id": int(note["id"]),
            "title": note["title"],
            "body": note["body"],
            "created_at": note["created_at"],
        }
        return RouteResult(route=decision.route, reason=decision.reason, result=result)

    result = {
        "status": "planned",
        "goal": goal,
        "next_step": "Review the goal and choose whether it should become a codex loop or self-improvement run.",
    }
    return RouteResult(route=decision.route, reason=decision.reason, result=result)


def handle_natural_language_request(
    goal: str,
    *,
    cwd: Path | str | None = None,
    db_path: Path = DB_PATH,
) -> int:
    routed = route_goal_request(goal, cwd=cwd, db_path=db_path)
    print(render_cli_response(routed))
    return 0


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _note_title_from_goal(goal: str) -> str:
    words = [word for word in goal.strip().split() if word]
    if not words:
        return "Captured note"
    return " ".join(words[:8])[:80]
