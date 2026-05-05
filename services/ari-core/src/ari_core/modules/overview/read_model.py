from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from ari_core.modules.skills import SkillManifest, list_skill_manifests


@dataclass(frozen=True, slots=True)
class OverviewSkill:
    skill_id: str
    name: str
    lifecycle_status: str
    implementation_status: str


@dataclass(frozen=True, slots=True)
class OverviewMetric:
    value: int | None
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class ARIOperatingOverview:
    generated_at: str
    system_label: str
    doctrine_summary: str
    active_skill_count: int
    prototype_skill_count: int
    candidate_skill_count: int
    active_skills: tuple[OverviewSkill, ...]
    prototype_skills: tuple[OverviewSkill, ...]
    candidate_skills: tuple[OverviewSkill, ...]
    pending_approval_count: OverviewMetric
    recent_coding_loop_count: OverviewMetric
    recent_memory_lesson_count: OverviewMetric
    self_documentation_status: str
    dashboard_mode: str
    authority_warning: str
    next_recommended_inspection: str
    read_model_notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_ari_operating_overview() -> ARIOperatingOverview:
    manifests = list_skill_manifests()
    active_skills = _skills_with_status(manifests, "active")
    prototype_skills = _skills_with_status(manifests, "prototype")
    candidate_skills = _skills_with_status(manifests, "candidate")

    return ARIOperatingOverview(
        generated_at=_now_iso(),
        system_label="ARI local-first operating overview",
        doctrine_summary=(
            "ARI is the brain for decisions, memory, planning, execution, verification, "
            "learning, authority, self-improvement, content generation, and skill "
            "orchestration. ACE is read-only interface in this dashboard phase."
        ),
        active_skill_count=len(active_skills),
        prototype_skill_count=len(prototype_skills),
        candidate_skill_count=len(candidate_skills),
        active_skills=active_skills,
        prototype_skills=prototype_skills,
        candidate_skills=candidate_skills,
        pending_approval_count=_unavailable_metric(
            "Pending approval aggregation is not wired into this overview read model yet."
        ),
        recent_coding_loop_count=_unavailable_metric(
            "Recent coding-loop aggregation is not wired into this overview read model yet."
        ),
        recent_memory_lesson_count=_unavailable_metric(
            "Recent lifecycle lesson aggregation is not wired into this overview read model yet."
        ),
        self_documentation_status=(
            "prototype: ContentSeed and ContentPackage generation are implemented; "
            "recording, export, upload, voice, and publishing are not implemented."
        ),
        dashboard_mode="read_only",
        authority_warning=(
            "ACE may display this overview but must not approve, reject, execute, "
            "advance chains, mutate memory, create skills, or own ARI state."
        ),
        next_recommended_inspection=(
            "Inspect skill readiness and missing-skill proposals, then connect live "
            "read-only approval, coding-loop, and memory summary counts through ARI-owned "
            "inspection surfaces."
        ),
        read_model_notes=(
            "Skill counts are live from the static ARI skill catalog.",
            "Approval, coding-loop, and memory counts are intentionally marked partial.",
            "This read model performs no execution, mutation, dynamic loading, or external calls.",
        ),
    )


def _skills_with_status(
    manifests: tuple[SkillManifest, ...],
    lifecycle_status: str,
) -> tuple[OverviewSkill, ...]:
    return tuple(
        OverviewSkill(
            skill_id=manifest.skill_id,
            name=manifest.name,
            lifecycle_status=manifest.lifecycle_status,
            implementation_status=manifest.implementation_status,
        )
        for manifest in manifests
        if manifest.lifecycle_status == lifecycle_status
    )


def _unavailable_metric(reason: str) -> OverviewMetric:
    return OverviewMetric(value=None, status="partial_unavailable", reason=reason)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
