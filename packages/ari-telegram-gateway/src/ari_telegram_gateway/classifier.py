from __future__ import annotations

import re

from ari_telegram_gateway.models import (
    AgentRole,
    ClassificationResult,
    IntentType,
    MediaStatus,
    RiskLevel,
    TranscriptStatus,
)

INSTAGRAM_PATTERN = re.compile(r"https?://(?:www\.)?(?:instagram\.com|instagr\.am)/\S+", re.I)


def classify_message(
    raw_text: str,
    *,
    has_media: bool = False,
    media_kinds: list[str] | None = None,
) -> ClassificationResult:
    text = _normalize(raw_text)
    media_kinds = media_kinds or []

    role = _assign_role(text)
    intent = _assign_intent(text, role=role, has_media=has_media, media_kinds=media_kinds)
    requires_approval = role is AgentRole.CTO_CODEX
    risk_level = RiskLevel.MEDIUM if requires_approval else RiskLevel.LOW
    next_action = _next_action_for(intent, role)
    source_platform = None
    media_status = MediaStatus.CAPTURED if has_media else MediaStatus.NONE
    transcript_status = TranscriptStatus.NONE

    if "video" in media_kinds or "voice" in media_kinds:
        transcript_status = TranscriptStatus.PENDING

    if INSTAGRAM_PATTERN.search(raw_text):
        source_platform = "instagram"
        media_status = MediaStatus.LINK_ONLY if not has_media else MediaStatus.CAPTURED
        if not has_media:
            transcript_status = TranscriptStatus.UNAVAILABLE
            next_action = "request_video_file_or_screen_recording_if_needed"

    return ClassificationResult(
        normalized_intent=intent,
        assigned_role=role,
        risk_level=risk_level,
        requires_approval=requires_approval,
        next_action=next_action,
        source_platform=source_platform,
        media_status=media_status,
        transcript_status=transcript_status,
    )


def _assign_role(text: str) -> AgentRole:
    if _contains_any(text, ["ceo"]):
        return AgentRole.CEO
    if _contains_any(text, ["cto", "codex"]):
        return AgentRole.CTO_CODEX
    if _contains_any(text, ["cpo"]):
        return AgentRole.CPO
    if _contains_any(text, ["cco"]):
        return AgentRole.CCO

    if _contains_any(
        text,
        [
            "code",
            "bug",
            "repo",
            "terminal",
            "api",
            "dashboard bug",
            "fix",
            "inspect",
            "test",
            "buttons disappeared",
        ],
    ):
        return AgentRole.CTO_CODEX
    if _contains_any(
        text,
        [
            "product",
            "design",
            "ux",
            "interface",
            "inspiration",
            "competitor reel",
            "instagram reel",
            "app flow",
            "dashboard feel",
        ],
    ):
        return AgentRole.CPO
    if _contains_any(
        text,
        ["content", "post", "caption", "hook", "audience", "positioning", "brand"],
    ):
        return AgentRole.CCO
    if _contains_any(text, ["research", "find", "look up", "compare", "investigate"]):
        return AgentRole.RESEARCH
    if _contains_any(text, ["remember", "save this", "store", "memory", "note this"]):
        return AgentRole.MEMORY
    if _contains_any(
        text,
        ["priority", "strategy", "decision", "should i", "next move", "tradeoff"],
    ):
        return AgentRole.CEO
    return AgentRole.OPERATOR


def _assign_intent(
    text: str, *, role: AgentRole, has_media: bool, media_kinds: list[str]
) -> IntentType:
    if role is AgentRole.CTO_CODEX:
        return IntentType.CODEX_TASK
    if "competitor" in text:
        return IntentType.COMPETITOR_INTEL
    if role is AgentRole.CPO and _contains_any(
        text,
        [
            "product",
            "design",
            "ux",
            "interface",
            "inspiration",
            "reel",
            "app flow",
            "dashboard feel",
        ],
    ):
        return IntentType.PRODUCT_INSPIRATION
    if role is AgentRole.CEO:
        return IntentType.STRATEGY_DECISION
    if role is AgentRole.CCO:
        return IntentType.CONTENT_STRATEGY
    if role is AgentRole.RESEARCH:
        return IntentType.RESEARCH_REQUEST
    if role is AgentRole.MEMORY:
        return IntentType.MEMORY_CAPTURE
    if has_media or media_kinds:
        return IntentType.MEDIA_INGEST
    if role is AgentRole.OPERATOR:
        return IntentType.OPERATOR_TASK
    return IntentType.UNKNOWN


def _next_action_for(intent: IntentType, role: AgentRole) -> str:
    if intent is IntentType.CODEX_TASK:
        return "create_pending_codex_task"
    if intent is IntentType.STRATEGY_DECISION:
        return "queue_for_strategy_review"
    if intent in {IntentType.PRODUCT_INSPIRATION, IntentType.COMPETITOR_INTEL}:
        return "queue_for_product_review"
    if intent is IntentType.CONTENT_STRATEGY:
        return "queue_for_content_review"
    if intent is IntentType.RESEARCH_REQUEST:
        return "queue_for_research"
    if intent is IntentType.MEMORY_CAPTURE:
        return "queue_for_memory_capture"
    if intent is IntentType.MEDIA_INGEST:
        return "queue_for_media_review"
    if role is AgentRole.OPERATOR:
        return "queue_for_operator_triage"
    return "queue_for_operator_triage"


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _contains_term(text: str, term: str) -> bool:
    if " " in term:
        return term in text
    return re.search(rf"\b{re.escape(term)}\b", text) is not None
