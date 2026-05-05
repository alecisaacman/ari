from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


class SkillRouteStatus(StrEnum):
    ROUTE_TO_SKILL = "route_to_skill"
    ASK_USER = "ask_user"
    MISSING_SKILL = "missing_skill"
    BLOCKED = "blocked"
    UNSAFE = "unsafe"


@dataclass(frozen=True, slots=True)
class SkillRoutingRecommendation:
    route_id: str
    goal: str
    status: SkillRouteStatus
    recommended_skill_id: str | None
    confidence: float
    reason: str
    matched_capabilities: tuple[str, ...]
    required_authority_boundary: str
    verification_expectation: str
    memory_effect_expectation: str
    missing_skill_candidate_id: str | None = None
    clarification_question: str | None = None
    created_at: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True, slots=True)
class _SkillProfile:
    skill_id: str
    capabilities: tuple[str, ...]
    authority_boundary: str
    verification_expectation: str
    memory_effect_expectation: str


CODING_LOOP = _SkillProfile(
    skill_id="ari.native.coding_loop",
    capabilities=(
        "bounded repository inspection",
        "bounded file write or patch proposal",
        "unit-test or ruff-backed verification",
        "approval-aware retry chain",
    ),
    authority_boundary=(
        "Must use ARI execution validation, safe command policy, and approval boundaries "
        "before mutation or approved retry execution."
    ),
    verification_expectation=(
        "Verify with existing bounded execution results and allowed local test/lint commands."
    ),
    memory_effect_expectation=(
        "Capture compact coding-loop lifecycle memory only after an inspected chain outcome."
    ),
)

SELF_DOCUMENTATION = _SkillProfile(
    skill_id="ari.native.self_documentation",
    capabilities=(
        "content seed generation from local evidence",
        "content package planning from seed evidence",
        "demo script and shot-list drafting",
        "redaction and claims-to-avoid review",
    ),
    authority_boundary=(
        "Read-only by default; approval required before recording, exporting, posting, "
        "uploading, or including sensitive data."
    ),
    verification_expectation=(
        "Verify claims against commits, tests, docs, execution traces, and current skill status."
    ),
    memory_effect_expectation=(
        "May create compact content-planning summaries; must not duplicate full traces."
    ),
)

MISSING_SKILL_CANDIDATES = {
    "file_organization": _SkillProfile(
        skill_id="ari.native.file_organization",
        capabilities=("local file organization", "dry-run move or cleanup proposal"),
        authority_boundary=(
            "Approval required before broad filesystem traversal, moves, copies, or deletes."
        ),
        verification_expectation=(
            "Would require before/after manifests and reversible dry-run plans."
        ),
        memory_effect_expectation="Would store compact organization rationale and outcomes.",
    ),
    "document_processing": _SkillProfile(
        skill_id="ari.native.document_processing",
        capabilities=("document or PDF summarization", "document extraction"),
        authority_boundary=(
            "Approval required before exposing, exporting, or mutating private documents."
        ),
        verification_expectation=(
            "Would require extracted-text evidence, file references, and readback checks."
        ),
        memory_effect_expectation="Would store compact document summary references only.",
    ),
}


def route_goal_to_skill(goal: str) -> SkillRoutingRecommendation:
    clean_goal = " ".join(goal.strip().split())
    normalized = clean_goal.lower()
    if not clean_goal:
        return _ask_user(clean_goal, "What goal should ARI route?")

    unsafe_reason = _unsafe_reason(normalized)
    if unsafe_reason:
        return _terminal(
            goal=clean_goal,
            status=SkillRouteStatus.UNSAFE,
            confidence=0.95,
            reason=unsafe_reason,
            authority_boundary="ARI must refuse goals that expose secrets or private data.",
            verification="No verification path is allowed for unsafe disclosure goals.",
            memory="No memory should be written from unsafe private data.",
        )

    blocked_reason = _blocked_reason(normalized)
    if blocked_reason:
        return _terminal(
            goal=clean_goal,
            status=SkillRouteStatus.BLOCKED,
            confidence=0.92,
            reason=blocked_reason,
            authority_boundary=(
                "This requires an authority surface that is not implemented in this slice."
            ),
            verification="No execution or external side effect should occur.",
            memory="At most store a compact blocked-goal summary if future memory capture exists.",
        )

    missing_candidate = _missing_skill_candidate(normalized)
    if missing_candidate:
        return _missing_skill(clean_goal, missing_candidate)

    coding_score = _score(normalized, _CODING_KEYWORDS)
    self_doc_score = _score(normalized, _SELF_DOCUMENTATION_KEYWORDS)

    if coding_score == 0 and self_doc_score == 0:
        return _ask_user(
            clean_goal,
            "Which outcome should ARI route this toward: code work, self-documentation, "
            "or a new skill?",
        )

    if coding_score >= self_doc_score:
        return _route_to_skill(clean_goal, CODING_LOOP, coding_score)
    return _route_to_skill(clean_goal, SELF_DOCUMENTATION, self_doc_score)


_CODING_KEYWORDS = (
    "write file",
    "patch",
    "fix failing",
    "unit test",
    "pytest",
    "ruff",
    "inspect recent code",
    "code changes",
    "repo",
    "repository",
    "implementation",
    "refactor",
    "bug",
)

_SELF_DOCUMENTATION_KEYWORDS = (
    "content seed",
    "content package",
    "demo script",
    "shot list",
    "voiceover",
    "linkedin post",
    "tiktok",
    "reel",
    "build summary",
    "recent commits",
    "last ari work",
    "self-documentation",
    "document its own build",
)

_UNSAFE_KEYWORDS = (
    "expose secrets",
    "leak secrets",
    "show api key",
    "show token",
    "scrape private data",
    "steal",
    "credential",
    "password",
)

_BLOCKED_KEYWORDS = (
    "publish publicly",
    "post publicly",
    "post to linkedin",
    "post to tiktok",
    "send email",
    "send emails",
    "delete files",
    "delete my",
    "rm -rf",
    "wipe",
)


def _route_to_skill(
    goal: str,
    profile: _SkillProfile,
    score: int,
) -> SkillRoutingRecommendation:
    confidence = min(0.95, 0.62 + (score * 0.08))
    return SkillRoutingRecommendation(
        route_id=f"skill-route-{uuid4()}",
        goal=goal,
        status=SkillRouteStatus.ROUTE_TO_SKILL,
        recommended_skill_id=profile.skill_id,
        confidence=round(confidence, 2),
        reason=f"Goal matches {profile.skill_id} capability keywords.",
        matched_capabilities=profile.capabilities,
        required_authority_boundary=profile.authority_boundary,
        verification_expectation=profile.verification_expectation,
        memory_effect_expectation=profile.memory_effect_expectation,
    )


def _missing_skill(goal: str, profile: _SkillProfile) -> SkillRoutingRecommendation:
    return SkillRoutingRecommendation(
        route_id=f"skill-route-{uuid4()}",
        goal=goal,
        status=SkillRouteStatus.MISSING_SKILL,
        recommended_skill_id=None,
        confidence=0.82,
        reason=f"Goal appears to require missing candidate skill {profile.skill_id}.",
        matched_capabilities=profile.capabilities,
        required_authority_boundary=profile.authority_boundary,
        verification_expectation=profile.verification_expectation,
        memory_effect_expectation=profile.memory_effect_expectation,
        missing_skill_candidate_id=profile.skill_id,
    )


def _ask_user(goal: str, question: str) -> SkillRoutingRecommendation:
    return SkillRoutingRecommendation(
        route_id=f"skill-route-{uuid4()}",
        goal=goal,
        status=SkillRouteStatus.ASK_USER,
        recommended_skill_id=None,
        confidence=0.35,
        reason="Goal is too broad or does not clearly match a known native skill.",
        matched_capabilities=(),
        required_authority_boundary="No authority boundary selected until the goal is clarified.",
        verification_expectation="No verification expectation selected until routing is clarified.",
        memory_effect_expectation="No memory effect expected from read-only routing.",
        clarification_question=question,
    )


def _terminal(
    *,
    goal: str,
    status: SkillRouteStatus,
    confidence: float,
    reason: str,
    authority_boundary: str,
    verification: str,
    memory: str,
) -> SkillRoutingRecommendation:
    return SkillRoutingRecommendation(
        route_id=f"skill-route-{uuid4()}",
        goal=goal,
        status=status,
        recommended_skill_id=None,
        confidence=confidence,
        reason=reason,
        matched_capabilities=(),
        required_authority_boundary=authority_boundary,
        verification_expectation=verification,
        memory_effect_expectation=memory,
    )


def _unsafe_reason(goal: str) -> str | None:
    if any(keyword in goal for keyword in _UNSAFE_KEYWORDS):
        return "Goal requests secret/private-data exposure or unsafe data handling."
    return None


def _blocked_reason(goal: str) -> str | None:
    if any(keyword in goal for keyword in _BLOCKED_KEYWORDS):
        return "Goal requires an external, destructive, or public side effect not available here."
    return None


def _missing_skill_candidate(goal: str) -> _SkillProfile | None:
    if any(keyword in goal for keyword in ("downloads folder", "organize files", "file organize")):
        return MISSING_SKILL_CANDIDATES["file_organization"]
    if any(keyword in goal for keyword in ("pdf", "docx", "this document", "document file")):
        return MISSING_SKILL_CANDIDATES["document_processing"]
    return None


def _score(goal: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword in goal)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
