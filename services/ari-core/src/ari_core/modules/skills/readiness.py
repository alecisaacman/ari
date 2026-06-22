from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from .catalog import SkillManifest, get_skill_manifest


class SkillReadinessStatus(StrEnum):
    ACTIVE = "active"
    PROTOTYPE = "prototype"
    CANDIDATE_NOT_READY = "candidate_not_ready"
    BLOCKED = "blocked"
    UNKNOWN_SKILL = "unknown_skill"


READINESS_GATES = (
    "manifest_exists",
    "authority_boundary_defined",
    "validation_rules_defined",
    "verification_defined",
    "memory_effect_defined",
    "inspection_surface_defined",
    "tests_defined",
    "implementation_exists",
    "no_bypass_of_ari_authority",
    "approval_boundary_clear",
)


@dataclass(frozen=True, slots=True)
class SkillReadinessReport:
    readiness_id: str
    skill_id: str
    status: SkillReadinessStatus
    lifecycle_status: str | None
    implementation_status: str | None
    reason: str
    missing_gates: tuple[str, ...]
    satisfied_gates: tuple[str, ...]
    required_authority_boundary: str | None
    required_verification: str | None
    required_memory_effect: str | None
    required_inspection_surface: tuple[str, ...]
    recommended_next_step: str
    can_route_goals_now: bool
    can_execute_now: bool
    can_promote_now: bool
    created_at: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


def evaluate_skill_readiness(skill_id: str) -> SkillReadinessReport:
    manifest = get_skill_manifest(skill_id)
    if manifest is None:
        return _unknown_skill(skill_id)

    satisfied_gates, missing_gates = _evaluate_gates(manifest)
    status = _status_for_manifest(manifest)
    return SkillReadinessReport(
        readiness_id=f"skill-readiness-{uuid4()}",
        skill_id=manifest.skill_id,
        status=status,
        lifecycle_status=manifest.lifecycle_status,
        implementation_status=manifest.implementation_status,
        reason=_reason_for_manifest(manifest, status),
        missing_gates=missing_gates,
        satisfied_gates=satisfied_gates,
        required_authority_boundary=manifest.authority_boundary,
        required_verification=manifest.verification_expectation,
        required_memory_effect=manifest.memory_effect_expectation,
        required_inspection_surface=manifest.inspection_surfaces,
        recommended_next_step=_recommended_next_step(manifest, status, missing_gates),
        can_route_goals_now=status in {
            SkillReadinessStatus.ACTIVE,
            SkillReadinessStatus.PROTOTYPE,
        },
        can_execute_now=status is SkillReadinessStatus.ACTIVE,
        can_promote_now=False,
    )


def _evaluate_gates(manifest: SkillManifest) -> tuple[tuple[str, ...], tuple[str, ...]]:
    gate_values = {
        "manifest_exists": True,
        "authority_boundary_defined": bool(manifest.authority_boundary),
        "validation_rules_defined": _implementation_exists(manifest),
        "verification_defined": bool(manifest.verification_expectation),
        "memory_effect_defined": bool(manifest.memory_effect_expectation),
        "inspection_surface_defined": bool(manifest.inspection_surfaces),
        "tests_defined": _implementation_exists(manifest),
        "implementation_exists": _implementation_exists(manifest),
        "no_bypass_of_ari_authority": bool(manifest.safety_constraints),
        "approval_boundary_clear": "approval" in manifest.authority_boundary.lower(),
    }
    satisfied = tuple(gate for gate in READINESS_GATES if gate_values[gate])
    missing = tuple(gate for gate in READINESS_GATES if not gate_values[gate])
    return satisfied, missing


def _status_for_manifest(manifest: SkillManifest) -> SkillReadinessStatus:
    if manifest.lifecycle_status == "blocked":
        return SkillReadinessStatus.BLOCKED
    if manifest.lifecycle_status == "active":
        return SkillReadinessStatus.ACTIVE
    if manifest.lifecycle_status == "prototype":
        return SkillReadinessStatus.PROTOTYPE
    return SkillReadinessStatus.CANDIDATE_NOT_READY


def _reason_for_manifest(
    manifest: SkillManifest,
    status: SkillReadinessStatus,
) -> str:
    if status is SkillReadinessStatus.ACTIVE:
        return "Skill is active in ARI's bounded authority spine."
    if status is SkillReadinessStatus.PROTOTYPE:
        return "Skill has a partial implementation, but is not promoted to active status."
    if status is SkillReadinessStatus.BLOCKED:
        return "Skill is blocked by unresolved authority, safety, or architecture gates."
    return f"Skill is cataloged as {manifest.lifecycle_status} but is not implemented."


def _recommended_next_step(
    manifest: SkillManifest,
    status: SkillReadinessStatus,
    missing_gates: tuple[str, ...],
) -> str:
    if status is SkillReadinessStatus.ACTIVE:
        return "Keep monitoring inspection, verification, and memory quality."
    if status is SkillReadinessStatus.PROTOTYPE:
        return "Define promotion criteria and prove missing gates before active status."
    if status is SkillReadinessStatus.BLOCKED:
        return "Resolve the blocking authority or safety issue before implementation."
    if missing_gates:
        return f"Implement and verify missing gates: {', '.join(missing_gates)}."
    return f"Design the next bounded implementation slice for {manifest.skill_id}."


def _implementation_exists(manifest: SkillManifest) -> bool:
    return manifest.implementation_status != "not implemented"


def _unknown_skill(skill_id: str) -> SkillReadinessReport:
    return SkillReadinessReport(
        readiness_id=f"skill-readiness-{uuid4()}",
        skill_id=skill_id,
        status=SkillReadinessStatus.UNKNOWN_SKILL,
        lifecycle_status=None,
        implementation_status=None,
        reason="Skill id is not present in the static ARI skill catalog.",
        missing_gates=READINESS_GATES,
        satisfied_gates=(),
        required_authority_boundary=None,
        required_verification=None,
        required_memory_effect=None,
        required_inspection_surface=(),
        recommended_next_step="Add a static skill manifest before evaluating readiness.",
        can_route_goals_now=False,
        can_execute_now=False,
        can_promote_now=False,
    )


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
