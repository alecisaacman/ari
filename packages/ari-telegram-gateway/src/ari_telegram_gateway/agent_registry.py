from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ari_telegram_gateway.models import AgentRole


class AgentDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: AgentRole
    display_name: str
    authority: str
    default_next_action: str
    can_execute_code: bool = False
    requires_approval_for_execution: bool = True


AGENT_REGISTRY: dict[AgentRole, AgentDescriptor] = {
    AgentRole.CEO: AgentDescriptor(
        role=AgentRole.CEO,
        display_name="ARI CEO",
        authority="Strategy, priorities, decisions, tradeoffs, and direction.",
        default_next_action="queue_for_strategy_review",
    ),
    AgentRole.CPO: AgentDescriptor(
        role=AgentRole.CPO,
        display_name="ARI CPO",
        authority="Product judgment, UX, design inspiration, competitor product intelligence.",
        default_next_action="queue_for_product_review",
    ),
    AgentRole.CTO_CODEX: AgentDescriptor(
        role=AgentRole.CTO_CODEX,
        display_name="ARI CTO / Codex",
        authority="Codebase inspection, implementation planning, bugs, tests, APIs, terminal work.",
        default_next_action="create_pending_codex_task",
        can_execute_code=False,
        requires_approval_for_execution=True,
    ),
    AgentRole.CCO: AgentDescriptor(
        role=AgentRole.CCO,
        display_name="ARI CCO",
        authority="Content strategy, captions, hooks, audience, positioning, and brand.",
        default_next_action="queue_for_content_review",
    ),
    AgentRole.RESEARCH: AgentDescriptor(
        role=AgentRole.RESEARCH,
        display_name="ARI Research",
        authority=(
            "Research requests, comparisons, external investigation, and intelligence briefs."
        ),
        default_next_action="queue_for_research",
    ),
    AgentRole.MEMORY: AgentDescriptor(
        role=AgentRole.MEMORY,
        display_name="ARI Memory",
        authority="Capture, preservation, notes, durable memory candidates, and retrieval cues.",
        default_next_action="queue_for_memory_capture",
    ),
    AgentRole.OPERATOR: AgentDescriptor(
        role=AgentRole.OPERATOR,
        display_name="ARI Operator",
        authority="General routing, follow-up, administrative tasks, and unresolved intake.",
        default_next_action="queue_for_operator_triage",
    ),
}


def get_agent(role: AgentRole) -> AgentDescriptor:
    return AGENT_REGISTRY[role]
