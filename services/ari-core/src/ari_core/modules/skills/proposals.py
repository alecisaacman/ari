from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from .catalog import SkillManifest, get_skill_manifest, list_skill_manifests
from .readiness import evaluate_skill_readiness


@dataclass(frozen=True, slots=True)
class MissingSkillProposal:
    proposal_id: str
    source_goal: str | None
    candidate_skill_id: str | None
    candidate_skill_name: str | None
    reason_skill_is_needed: str
    current_readiness_status: str
    missing_gates: tuple[str, ...]
    proposed_first_slice: str
    proposed_first_slice_scope: str
    authority_boundary: str | None
    approval_requirements: tuple[str, ...]
    validation_requirements: tuple[str, ...]
    verification_requirements: tuple[str, ...]
    memory_effects: tuple[str, ...]
    inspection_surfaces: tuple[str, ...]
    safety_constraints: tuple[str, ...]
    explicit_non_goals: tuple[str, ...]
    recommended_tests: tuple[str, ...]
    suggested_docs: tuple[str, ...]
    implementation_risk: str
    user_approval_required_before_building: bool
    created_at: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def propose_missing_skill(
    *,
    goal: str | None = None,
    skill_id: str | None = None,
) -> MissingSkillProposal:
    clean_goal = " ".join((goal or "").strip().split()) or None
    candidate = _candidate_from_inputs(clean_goal, skill_id)
    if candidate is None:
        return _clarification_proposal(clean_goal, skill_id)

    readiness = evaluate_skill_readiness(candidate.skill_id)
    template = _template_for(candidate.skill_id)
    return MissingSkillProposal(
        proposal_id=f"missing-skill-proposal-{uuid4()}",
        source_goal=clean_goal,
        candidate_skill_id=candidate.skill_id,
        candidate_skill_name=candidate.name,
        reason_skill_is_needed=_reason_skill_is_needed(candidate, clean_goal),
        current_readiness_status=readiness.status.value,
        missing_gates=readiness.missing_gates,
        proposed_first_slice=template["first_slice"],
        proposed_first_slice_scope=template["scope"],
        authority_boundary=candidate.authority_boundary,
        approval_requirements=template["approval_requirements"],
        validation_requirements=template["validation_requirements"],
        verification_requirements=(candidate.verification_expectation,),
        memory_effects=(candidate.memory_effect_expectation,),
        inspection_surfaces=candidate.inspection_surfaces,
        safety_constraints=candidate.safety_constraints,
        explicit_non_goals=template["explicit_non_goals"],
        recommended_tests=template["recommended_tests"],
        suggested_docs=candidate.docs_refs,
        implementation_risk=template["implementation_risk"],
        user_approval_required_before_building=True,
    )


def _candidate_from_inputs(goal: str | None, skill_id: str | None) -> SkillManifest | None:
    if skill_id:
        manifest = get_skill_manifest(skill_id)
        if manifest and manifest.lifecycle_status == "candidate":
            return manifest
        return None
    if not goal:
        return None

    normalized = goal.lower()
    # Specific side-effect intents are mapped to their candidate skill, but the proposed
    # first slice remains read-only and explicitly excludes the unsafe action.
    if any(keyword in normalized for keyword in ("email", "inbox", "calendar", "meeting")):
        return get_skill_manifest("ari.native.email_calendar_triage")
    for manifest in list_skill_manifests():
        if manifest.lifecycle_status != "candidate":
            continue
        if _score(normalized, manifest.allowed_goal_patterns):
            return manifest
    return None


def _template_for(skill_id: str) -> dict[str, tuple[str, ...] | str]:
    templates: dict[str, dict[str, tuple[str, ...] | str]] = {
        "ari.native.file_organization": {
            "first_slice": "Read-only local file scan, classification, and organization proposal.",
            "scope": (
                "Inspect a user-approved directory, classify files by type/date/project hints, "
                "and return a dry-run organization plan. Do not move, copy, rename, "
                "or delete files."
            ),
            "approval_requirements": (
                "User must approve the directory to inspect.",
                "Separate approval is required before any future file mutation.",
            ),
            "validation_requirements": (
                "Reject paths outside the approved root.",
                "Reject hidden mutation operations.",
                "Limit traversal depth and result count.",
            ),
            "explicit_non_goals": (
                "No moving files.",
                "No deleting files.",
                "No broad filesystem traversal.",
            ),
            "recommended_tests": (
                "Read-only scan does not mutate files.",
                "Traversal stays inside approved root.",
                "Dry-run plan is inspectable and deterministic.",
            ),
            "implementation_risk": "Medium: filesystem privacy and mutation safety must be proven.",
        },
        "ari.native.document_processing": {
            "first_slice": "Read-only document extraction and summary preview.",
            "scope": (
                "Read one user-provided local document/PDF, extract text or metadata, and produce "
                "a grounded summary with file references. Do not upload, mutate, or export files."
            ),
            "approval_requirements": (
                "User must approve each source document.",
                "Separate approval is required before export or mutation.",
            ),
            "validation_requirements": (
                "Reject missing files and unsupported file types.",
                "Reject external upload paths.",
                "Limit extracted text length stored in memory.",
            ),
            "explicit_non_goals": (
                "No external upload.",
                "No file mutation.",
                "No unsupported claims beyond extracted evidence.",
            ),
            "recommended_tests": (
                "Read-only extraction preserves source file.",
                "Summary cites extracted evidence.",
                "Unsupported files fail closed.",
            ),
            "implementation_risk": (
                "Medium: private document handling and extraction fidelity matter."
            ),
        },
        "ari.native.research_gathering": {
            "first_slice": "Read-only research plan and source collection proposal.",
            "scope": (
                "Create a bounded research plan and, after explicit network approval in a later "
                "slice, collect cited sources. No outreach, paid services, or account actions."
            ),
            "approval_requirements": (
                "Approval required before any external network access.",
                "Approval required before storing sensitive research context.",
            ),
            "validation_requirements": (
                "Require source URLs and timestamps for factual claims.",
                "Respect quote limits.",
                "Reject uncited conclusions.",
            ),
            "explicit_non_goals": (
                "No outreach.",
                "No account login.",
                "No paid-service use.",
            ),
            "recommended_tests": (
                "Plan generation is read-only.",
                "Source records require citations.",
                "No network call occurs without approval.",
            ),
            "implementation_risk": (
                "Medium-high: source quality and network authority must be explicit."
            ),
        },
        "ari.native.email_calendar_triage": {
            "first_slice": "Read-only email/calendar triage design and dry-run summary.",
            "scope": (
                "Design a connector-gated triage surface that can summarize approved "
                "inbox/calendar metadata later. Do not send, schedule, modify, archive, "
                "or store private content."
            ),
            "approval_requirements": (
                "Explicit approval required before reading connected accounts.",
                "Separate approval required before sending messages or changing calendar events.",
            ),
            "validation_requirements": (
                "Require connector-scoped account access.",
                "Reject send/schedule/archive/delete actions in first slice.",
                "Redact private content from durable memory by default.",
            ),
            "explicit_non_goals": (
                "No sending emails.",
                "No event creation or modification.",
                "No private content storage by default.",
            ),
            "recommended_tests": (
                "Send/schedule goals produce read-only triage proposal only.",
                "No connector call occurs without approval.",
                "Private content is not persisted by default.",
            ),
            "implementation_risk": (
                "High: private account access and outbound actions require strict authority."
            ),
        },
    }
    default = {
        "first_slice": "Read-only capability design and manifest hardening.",
        "scope": (
            "Define bounded inputs, outputs, validation, verification, authority, memory, and "
            "inspection before implementation. Do not execute the candidate skill."
        ),
        "approval_requirements": (
            "User approval required before implementation work.",
            "Separate approval required before any side effect.",
        ),
        "validation_requirements": (
            "Define fail-closed input validation.",
            "Define authority checks before future execution.",
        ),
        "explicit_non_goals": (
            "No skill activation.",
            "No execution.",
            "No dynamic loading.",
        ),
        "recommended_tests": (
            "Manifest is inspectable.",
            "Read-only proposal is JSON serializable.",
            "Unsafe actions fail closed.",
        ),
        "implementation_risk": "Unknown until the skill-specific authority boundary is proven.",
    }
    return templates.get(skill_id, default)


def _clarification_proposal(
    goal: str | None,
    skill_id: str | None,
) -> MissingSkillProposal:
    return MissingSkillProposal(
        proposal_id=f"missing-skill-proposal-{uuid4()}",
        source_goal=goal,
        candidate_skill_id=None,
        candidate_skill_name=None,
        reason_skill_is_needed=(
            "No safe candidate skill could be selected from the static catalog."
        ),
        current_readiness_status="unknown_skill" if skill_id else "ask_user",
        missing_gates=(
            "manifest_exists",
            "authority_boundary_defined",
            "validation_rules_defined",
            "verification_defined",
            "memory_effect_defined",
            "inspection_surface_defined",
            "tests_defined",
            "implementation_exists",
            "approval_boundary_clear",
        ),
        proposed_first_slice="Ask the user to clarify the desired bounded capability.",
        proposed_first_slice_scope=(
            "No implementation proposal is safe until ARI can identify the skill class, "
            "authority boundary, verification method, and memory effect."
        ),
        authority_boundary=None,
        approval_requirements=("User clarification required before any build proposal.",),
        validation_requirements=("Reject broad or ambiguous goals until clarified.",),
        verification_requirements=(
            "No verification can be defined until the skill class is known.",
        ),
        memory_effects=("No memory effect expected from read-only clarification.",),
        inspection_surfaces=(),
        safety_constraints=(
            "No execution.",
            "No dynamic loading.",
            "No automatic skill creation.",
        ),
        explicit_non_goals=(
            "Do not build a skill automatically.",
            "Do not infer broad authority from an ambiguous goal.",
        ),
        recommended_tests=("Clarification proposal is JSON serializable.",),
        suggested_docs=("docs/skills/skill-inventory.md",),
        implementation_risk="High until the goal is clarified.",
        user_approval_required_before_building=True,
    )


def _reason_skill_is_needed(manifest: SkillManifest, goal: str | None) -> str:
    if goal:
        return f"Goal appears to require {manifest.skill_id}: {goal}"
    return f"Skill {manifest.skill_id} is cataloged but not active."


def _score(goal: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword in goal)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
