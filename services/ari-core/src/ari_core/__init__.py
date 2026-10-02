"""ARI core service package."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "ApprovalWorkflowResult": ("ari_core.approvals", "ApprovalWorkflowResult"),
    "BrainResponse": ("ari_core.brain", "BrainResponse"),
    "CreateOpenLoopInput": ("ari_core.state", "CreateOpenLoopInput"),
    "DailyStateUpdate": ("ari_core.state", "DailyStateUpdate"),
    "MCP_BETA_HEADER": ("ari_core.skills", "MCP_BETA_HEADER"),
    "OrchestrationRunComparison": ("ari_core.history", "OrchestrationRunComparison"),
    "OrchestrationRunDetails": ("ari_core.history", "OrchestrationRunDetails"),
    "RunSignalOrchestrationInput": (
        "ari_core.orchestration",
        "RunSignalOrchestrationInput",
    ),
    "RunSignalOrchestrationResult": (
        "ari_core.orchestration",
        "RunSignalOrchestrationResult",
    ),
    "StateMutationResult": ("ari_core.state", "StateMutationResult"),
    "WeeklyPlanningUpdate": ("ari_core.state", "WeeklyPlanningUpdate"),
    "WeeklyReflectionUpdate": ("ari_core.state", "WeeklyReflectionUpdate"),
    "approve_pending_approval": ("ari_core.approvals", "approve_pending_approval"),
    "build_controller_decision": ("ari_core.decision_translate", "build_controller_decision"),
    "build_mcp_request_args": ("ari_core.skills", "build_mcp_request_args"),
    "compare_latest_two_runs": ("ari_core.history", "compare_latest_two_runs"),
    "create_open_loop": ("ari_core.state", "create_open_loop"),
    "deny_pending_approval": ("ari_core.approvals", "deny_pending_approval"),
    "evaluate_decision_authority": ("ari_core.authority", "evaluate_decision_authority"),
    "extract_resolved_skill_invocations": (
        "ari_core.skills",
        "extract_resolved_skill_invocations",
    ),
    "get_alert_details": ("ari_core.history", "get_alert_details"),
    "get_conversation_state": ("ari_core.memory", "get_conversation_state"),
    "get_daily_state": ("ari_core.state", "get_daily_state"),
    "get_latest_run_details": ("ari_core.history", "get_latest_run_details"),
    "get_previous_run_details": ("ari_core.history", "get_previous_run_details"),
    "get_signal_details": ("ari_core.history", "get_signal_details"),
    "get_weekly_state": ("ari_core.state", "get_weekly_state"),
    "list_open_loops": ("ari_core.state", "list_open_loops"),
    "list_pending_approvals": ("ari_core.approvals", "list_pending_approvals"),
    "make_tool_dispatcher": ("ari_core.brain", "make_tool_dispatcher"),
    "record_skill_invocation": ("ari_core.skills", "record_skill_invocation"),
    "register_skill": ("ari_core.skills", "register_skill"),
    "respond_to_message": ("ari_core.brain", "respond_to_message"),
    "resume_controller_cycle": ("ari_core.controller", "resume_controller_cycle"),
    "resolve_open_loop": ("ari_core.state", "resolve_open_loop"),
    "run_controller_cycle": ("ari_core.controller", "run_controller_cycle"),
    "run_signal_orchestration": ("ari_core.orchestration", "run_signal_orchestration"),
    "save_conversation_state": ("ari_core.memory", "save_conversation_state"),
    "update_daily_state": ("ari_core.state", "update_daily_state"),
    "update_weekly_plan": ("ari_core.state", "update_weekly_plan"),
    "update_weekly_reflection": ("ari_core.state", "update_weekly_reflection"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    """Load public exports on demand without hiding dependency import errors."""
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
