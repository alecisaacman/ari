from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ari_core.core.paths import DB_PATH
from ari_core.modules.self_documentation import (
    ContentIdea,
    generate_content_idea_bank,
)


@dataclass(frozen=True, slots=True)
class ContentIdeaSummary:
    idea_id: str
    title: str
    hook: str
    platform_fit: tuple[str, ...]
    audience: str
    source_artifact_ids: tuple[str, ...]
    source_artifact_types: tuple[str, ...]
    proof_point_count: int
    risk_level: str
    recording_difficulty: str
    edit_complexity: str
    recommended_priority: int
    reason_for_priority: str
    visual_plan: str
    script_angle: str
    redaction_note_count: int
    claims_to_avoid_count: int
    inspection_hint: str
    readiness_status: str


@dataclass(frozen=True, slots=True)
class ContentIdeasReadModel:
    generated_at: str
    total_idea_count: int
    recent_ideas: tuple[ContentIdeaSummary, ...]
    unavailable_reason: str | None
    source_of_truth: str
    authority_warning: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_content_ideas_read_model(
    *,
    db_path: Path = DB_PATH,
    limit: int = 20,
) -> ContentIdeasReadModel:
    source_of_truth = "ARI-owned self-documentation ContentIdeaBank"
    authority_warning = (
        "This read model is inspection-only. ACE may display content ideas but "
        "must not generate ideas independently, mutate artifacts, record, edit, "
        "upload, publish, call external services, or own content truth."
    )
    idea_bank = generate_content_idea_bank(db_path=db_path, limit=limit)
    if idea_bank.unavailable_reason:
        return ContentIdeasReadModel(
            generated_at=idea_bank.generated_at,
            total_idea_count=0,
            recent_ideas=(),
            unavailable_reason=idea_bank.unavailable_reason,
            source_of_truth=source_of_truth,
            authority_warning=authority_warning,
        )

    ideas = tuple(_summarize_idea(idea) for idea in idea_bank.ideas[:limit])
    return ContentIdeasReadModel(
        generated_at=idea_bank.generated_at,
        total_idea_count=idea_bank.total_idea_count,
        recent_ideas=ideas,
        unavailable_reason=None,
        source_of_truth=source_of_truth,
        authority_warning=authority_warning,
    )


def _summarize_idea(idea: ContentIdea) -> ContentIdeaSummary:
    return ContentIdeaSummary(
        idea_id=idea.idea_id,
        title=idea.title,
        hook=idea.hook,
        platform_fit=idea.platform_fit,
        audience=idea.audience,
        source_artifact_ids=idea.source_artifact_ids,
        source_artifact_types=idea.source_artifact_types,
        proof_point_count=len(idea.proof_points),
        risk_level=idea.risk_level,
        recording_difficulty=idea.recording_difficulty,
        edit_complexity=idea.edit_complexity,
        recommended_priority=idea.recommended_priority,
        reason_for_priority=idea.reason_for_priority,
        visual_plan=idea.visual_plan,
        script_angle=idea.script_angle,
        redaction_note_count=len(idea.redaction_notes),
        claims_to_avoid_count=len(idea.claims_to_avoid),
        inspection_hint=f"api self-doc ideas list --json # idea_id={idea.idea_id}",
        readiness_status=_readiness_status(idea),
    )


def _readiness_status(idea: ContentIdea) -> str:
    if not idea.title.strip() or not idea.hook.strip() or not idea.proof_points:
        return "partial"
    if idea.risk_level in {"medium", "high"}:
        return "needs_redaction_review"
    return "ready_for_review"
