from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ari_core.core.paths import DB_PATH
from ari_core.modules.execution.coding_loop import list_coding_loop_retry_approvals
from ari_core.modules.execution.inspection import list_coding_loop_results
from ari_core.modules.memory.db import list_memory_blocks
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
    recent_lifecycle_lesson_count: OverviewMetric
    recent_memory_lesson_count: OverviewMetric
    counts_generated_from_live_sources: bool
    unavailable_counts: tuple[str, ...]
    partial_counts_reason: str | None
    self_documentation_status: str
    dashboard_mode: str
    authority_warning: str
    next_recommended_inspection: str
    read_model_notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_ari_operating_overview(
    *,
    db_path: Path = DB_PATH,
) -> ARIOperatingOverview:
    manifests = list_skill_manifests()
    active_skills = _skills_with_status(manifests, "active")
    prototype_skills = _skills_with_status(manifests, "prototype")
    candidate_skills = _skills_with_status(manifests, "candidate")
    pending_approval_count = _pending_approval_count(db_path)
    recent_coding_loop_count = _recent_coding_loop_count(db_path)
    recent_lifecycle_lesson_count = _recent_lifecycle_lesson_count(db_path)
    unavailable_counts = tuple(
        name
        for name, metric in (
            ("pending_approval_count", pending_approval_count),
            ("recent_coding_loop_count", recent_coding_loop_count),
            ("recent_lifecycle_lesson_count", recent_lifecycle_lesson_count),
        )
        if metric.value is None
    )

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
        pending_approval_count=pending_approval_count,
        recent_coding_loop_count=recent_coding_loop_count,
        recent_lifecycle_lesson_count=recent_lifecycle_lesson_count,
        recent_memory_lesson_count=recent_lifecycle_lesson_count,
        counts_generated_from_live_sources=not unavailable_counts,
        unavailable_counts=unavailable_counts,
        partial_counts_reason=(
            None
            if not unavailable_counts
            else f"Unavailable count sources: {', '.join(unavailable_counts)}."
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
            "Approval, coding-loop, and lifecycle lesson counts are live when their "
            "ARI-owned stores are readable.",
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


def _live_metric(value: int, reason: str) -> OverviewMetric:
    return OverviewMetric(value=value, status="live", reason=reason)


def _pending_approval_count(db_path: Path) -> OverviewMetric:
    try:
        approvals = list_coding_loop_retry_approvals(limit=200, db_path=db_path)
    except Exception as error:  # pragma: no cover - exercised through tests via monkeypatch.
        return _unavailable_metric(
            f"Pending retry approval count is unavailable: {type(error).__name__}: {error}"
        )
    pending = sum(1 for approval in approvals if approval.approval_status == "pending")
    return _live_metric(pending, "Live count from durable coding-loop retry approvals.")


def _recent_coding_loop_count(db_path: Path) -> OverviewMetric:
    try:
        results = list_coding_loop_results(limit=20, db_path=db_path)
    except Exception as error:  # pragma: no cover - exercised through tests via monkeypatch.
        return _unavailable_metric(
            f"Recent coding-loop count is unavailable: {type(error).__name__}: {error}"
        )
    return _live_metric(len(results), "Live count from durable coding-loop result inspection.")


def _recent_lifecycle_lesson_count(db_path: Path) -> OverviewMetric:
    try:
        blocks = list_memory_blocks(limit=50, db_path=db_path)
    except Exception as error:  # pragma: no cover - exercised through tests via monkeypatch.
        return _unavailable_metric(
            f"Recent lifecycle lesson count is unavailable: {type(error).__name__}: {error}"
        )
    lessons = sum(1 for block in blocks if block["kind"] == "coding_loop_chain_lifecycle_summary")
    return _live_metric(lessons, "Live count from canonical memory lifecycle blocks.")


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
