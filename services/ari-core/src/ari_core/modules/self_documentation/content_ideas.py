from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from ari_core.core.paths import DB_PATH

from .content_package import ContentPackage
from .content_seed import ContentSeed
from .storage import list_content_packages, list_content_seeds


@dataclass(frozen=True, slots=True)
class ContentIdea:
    idea_id: str
    title: str
    hook: str
    platform_fit: tuple[str, ...]
    audience: str
    source_artifact_ids: tuple[str, ...]
    source_artifact_types: tuple[str, ...]
    proof_points: tuple[str, ...]
    visual_plan: str
    suggested_shot_list: tuple[str, ...]
    script_angle: str
    recording_difficulty: str
    edit_complexity: str
    risk_level: str
    redaction_notes: tuple[str, ...]
    claims_to_avoid: tuple[str, ...]
    recommended_priority: int
    reason_for_priority: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ContentIdeaBank:
    generated_at: str
    total_idea_count: int
    ideas: tuple[ContentIdea, ...]
    source_of_truth: str
    unavailable_reason: str | None
    authority_warning: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def generate_content_idea_bank(
    *,
    db_path: Path = DB_PATH,
    limit: int = 20,
) -> ContentIdeaBank:
    source_of_truth = "persisted self-documentation ContentSeed and ContentPackage artifacts"
    authority_warning = (
        "This idea bank is read-only content planning. ARI may propose grounded "
        "content ideas, but it must not record, edit, upload, publish, mutate "
        "artifacts, call external services, or let ACE own content truth."
    )
    try:
        seeds = list_content_seeds(limit=limit, db_path=db_path)
        packages = list_content_packages(limit=limit, db_path=db_path)
    except Exception as error:  # pragma: no cover - exercised through monkeypatch tests.
        return ContentIdeaBank(
            generated_at=_now_iso(),
            total_idea_count=0,
            ideas=(),
            source_of_truth=source_of_truth,
            unavailable_reason=(
                f"Content ideas are unavailable: {type(error).__name__}: {error}"
            ),
            authority_warning=authority_warning,
        )

    ideas = tuple(
        sorted(
            (
                *(_idea_from_seed(seed) for seed in seeds),
                *(_idea_from_package(package) for package in packages),
            ),
            key=lambda idea: (
                -idea.recommended_priority,
                idea.risk_level,
                idea.title,
                idea.idea_id,
            ),
        )[:limit]
    )
    return ContentIdeaBank(
        generated_at=_now_iso(),
        total_idea_count=len(ideas),
        ideas=ideas,
        source_of_truth=source_of_truth,
        unavailable_reason=None,
        authority_warning=authority_warning,
    )


def _idea_from_seed(seed: ContentSeed) -> ContentIdea:
    category = _category(seed.title, seed.one_sentence_summary, seed.demo_idea, *seed.source_files)
    risk_level = _risk_level((*seed.risk_notes, *seed.redaction_notes))
    proof_points = _proof_points(seed.proof_points)
    visual_moments = _visual_moments(seed.visual_moments)
    title = _title(category, seed.title)
    priority = _priority(
        proof_point_count=len(proof_points),
        visual_count=len(visual_moments),
        risk_level=risk_level,
        has_package=False,
    )
    return ContentIdea(
        idea_id=_idea_id("content_seed", seed.seed_id, category),
        title=title,
        hook=_hook(category, seed.hook_options, fallback=seed.one_sentence_summary),
        platform_fit=_platform_fit(category),
        audience=_audience(category),
        source_artifact_ids=(seed.seed_id,),
        source_artifact_types=("content_seed",),
        proof_points=proof_points,
        visual_plan=_visual_plan(category, visual_moments),
        suggested_shot_list=_seed_shots(seed, visual_moments),
        script_angle=seed.demo_idea,
        recording_difficulty=_recording_difficulty(visual_moments),
        edit_complexity="low" if len(visual_moments) <= 2 else "medium",
        risk_level=risk_level,
        redaction_notes=_redaction_notes(seed.redaction_notes, seed.risk_notes),
        claims_to_avoid=_claims_to_avoid(seed.claims_to_avoid),
        recommended_priority=priority,
        reason_for_priority=_priority_reason(priority, risk_level, has_package=False),
        created_at=seed.created_at,
    )


def _idea_from_package(package: ContentPackage) -> ContentIdea:
    category = _category(package.title, package.content_angle, package.voiceover_draft)
    risk_level = _risk_level((*package.redaction_checklist, *package.claims_to_avoid))
    shot_list = tuple(shot.suggested_visual for shot in package.shot_list if shot.suggested_visual)
    proof_points = tuple(shot.narration for shot in package.shot_list if shot.narration)[:3]
    priority = _priority(
        proof_point_count=len(proof_points),
        visual_count=len(shot_list),
        risk_level=risk_level,
        has_package=True,
    )
    return ContentIdea(
        idea_id=_idea_id("content_package", package.package_id, category),
        title=_title(category, package.title),
        hook=_first_sentence(package.thirty_second_vertical_script) or package.title,
        platform_fit=_platform_fit(category),
        audience=_audience(category),
        source_artifact_ids=(package.package_id, package.source_seed_id),
        source_artifact_types=("content_package", "content_seed"),
        proof_points=_proof_points(proof_points),
        visual_plan=_visual_plan(category, shot_list),
        suggested_shot_list=_package_shots(package),
        script_angle=package.content_angle,
        recording_difficulty=_recording_difficulty(shot_list),
        edit_complexity="medium" if len(package.shot_list) >= 3 else "low",
        risk_level=risk_level,
        redaction_notes=tuple(dict.fromkeys(package.redaction_checklist)),
        claims_to_avoid=_claims_to_avoid(package.claims_to_avoid),
        recommended_priority=priority,
        reason_for_priority=_priority_reason(priority, risk_level, has_package=True),
        created_at=package.created_at,
    )


def _category(*values: str) -> str:
    text = " ".join(values).lower()
    categories = (
        ("approval_gates", ("approval", "authority", "retry")),
        ("read_only_ace_dashboard", ("ace", "dashboard", "read-only", "read model")),
        ("coding_loop_chain_inspection", ("coding-loop", "coding loop", "chain")),
        ("lifecycle_lessons", ("lifecycle", "lesson", "memory", "learning")),
        ("self_documenting_software", ("self-documentation", "content seed", "content package")),
        ("local_first_ai", ("local", "sqlite", "durable", "persist")),
        ("bounded_skills", ("skill", "missing-skill", "router", "catalog")),
    )
    for category, keywords in categories:
        if any(keyword in text for keyword in keywords):
            return category
    return "self_documenting_software"


def _title(category: str, fallback_title: str) -> str:
    titles = {
        "approval_gates": "Show ARI's approval boundary before autonomy",
        "read_only_ace_dashboard": "Show ACE as a read-only window into ARI",
        "coding_loop_chain_inspection": "Show a coding-loop chain as an inspectable story",
        "lifecycle_lessons": "Show ARI turning execution outcomes into lessons",
        "self_documenting_software": "Show ARI documenting its own build from evidence",
        "local_first_ai": "Show local-first ARI state without cloud dependency claims",
        "bounded_skills": "Show ARI treating skills as bounded capabilities",
    }
    return titles.get(category, fallback_title)


def _hook(category: str, hook_options: tuple[str, ...], *, fallback: str) -> str:
    if hook_options:
        return hook_options[0]
    hooks = {
        "approval_gates": "Autonomy is only useful if the stop signs are visible.",
        "read_only_ace_dashboard": (
            "This is what an AI interface looks like when it is not the brain."
        ),
        "coding_loop_chain_inspection": "Instead of hiding the loop, ARI shows the whole chain.",
        "lifecycle_lessons": "A useful AI system should remember what its attempts taught it.",
        "self_documenting_software": "ARI can turn real commits into factual build stories.",
        "local_first_ai": "The important state lives locally before any surface displays it.",
        "bounded_skills": "A skill is a capability, not a second brain.",
    }
    return hooks.get(category, fallback)


def _platform_fit(category: str) -> tuple[str, ...]:
    if category in {"read_only_ace_dashboard", "coding_loop_chain_inspection"}:
        return ("LinkedIn", "long-form demo", "TikTok/Reel")
    if category in {"approval_gates", "bounded_skills"}:
        return ("LinkedIn", "TikTok/Reel")
    return ("TikTok/Reel", "LinkedIn", "long-form demo")


def _audience(category: str) -> str:
    if category in {"approval_gates", "bounded_skills"}:
        return "builders evaluating safe autonomous systems"
    if category == "read_only_ace_dashboard":
        return "product-minded AI builders and operators"
    if category == "local_first_ai":
        return "technical users who care about local-first AI architecture"
    return "people following ARI's build process"


def _visual_plan(category: str, visual_moments: tuple[str, ...]) -> str:
    prefix = {
        "approval_gates": "Show the approval artifact, status, and disabled controls.",
        "read_only_ace_dashboard": "Show ACE displaying ARI-owned read models without controls.",
        "coding_loop_chain_inspection": "Show the chain id, terminal status, and inspection hint.",
        "lifecycle_lessons": "Show the lifecycle lesson summary next to its source chain.",
        "self_documenting_software": "Show source commits becoming reviewable content artifacts.",
        "local_first_ai": "Show local persisted state and CLI/API inspection output.",
        "bounded_skills": "Show the skill catalog and missing-skill proposal boundary.",
    }.get(category, "Show the artifact evidence and read-only inspection output.")
    if not visual_moments:
        return prefix
    return f"{prefix} Use these concrete moments: {'; '.join(visual_moments[:3])}."


def _seed_shots(seed: ContentSeed, visual_moments: tuple[str, ...]) -> tuple[str, ...]:
    shots = [
        f"Open with the persisted ContentSeed title: {seed.title}",
        f"Show source evidence from {seed.source_commit_range}.",
        "Show proof_points, redaction_notes, and claims_to_avoid.",
    ]
    shots.extend(visual_moments[:2])
    return tuple(dict.fromkeys(shots))


def _package_shots(package: ContentPackage) -> tuple[str, ...]:
    shots = [
        f"{shot.label}: {shot.suggested_visual} — {shot.narration}"
        for shot in package.shot_list
    ]
    shots.append("End on approval gates: recording and posting remain disabled.")
    return tuple(dict.fromkeys(shots))


def _proof_points(values: tuple[str, ...]) -> tuple[str, ...]:
    if values:
        return tuple(dict.fromkeys(values[:4]))
    return ("No proof points are available; keep this idea internal until evidence exists.",)


def _visual_moments(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value.strip()))


def _redaction_notes(
    redaction_notes: tuple[str, ...],
    risk_notes: tuple[str, ...],
) -> tuple[str, ...]:
    notes = tuple(dict.fromkeys((*redaction_notes, *risk_notes)))
    return notes or ("Review artifact for secrets, private paths, and unsupported claims.",)


def _claims_to_avoid(values: tuple[str, ...]) -> tuple[str, ...]:
    baseline = (
        "Do not claim ARI records, edits, uploads, publishes, or posts content in this slice.",
        "Do not claim unattended autonomy beyond the approved ARI authority boundary.",
    )
    return tuple(dict.fromkeys((*values, *baseline)))


def _risk_level(values: tuple[str, ...]) -> str:
    text = " ".join(values).lower()
    if any(term in text for term in ("api key", "secret", "token", "credential", ".env")):
        return "high"
    if any(term in text for term in ("private", "email", "redact", "personal")):
        return "medium"
    return "low"


def _priority(
    *,
    proof_point_count: int,
    visual_count: int,
    risk_level: str,
    has_package: bool,
) -> int:
    priority = 40
    priority += min(proof_point_count, 4) * 10
    priority += min(visual_count, 3) * 8
    if has_package:
        priority += 15
    if risk_level == "medium":
        priority -= 15
    if risk_level == "high":
        priority -= 35
    return max(1, min(priority, 100))


def _priority_reason(priority: int, risk_level: str, *, has_package: bool) -> str:
    evidence = (
        "ContentPackage includes scripts and shots"
        if has_package
        else "ContentSeed includes source evidence"
    )
    return (
        f"{evidence}; risk is {risk_level}; deterministic priority is {priority}. "
        "Record only after manual approval and redaction review."
    )


def _recording_difficulty(visual_moments: tuple[str, ...]) -> str:
    if len(visual_moments) >= 3:
        return "medium"
    return "low"


def _first_sentence(text: str) -> str:
    line = next((item.strip() for item in text.splitlines() if item.strip()), "")
    if "." in line:
        return line.split(".", maxsplit=1)[0].strip() + "."
    return line


def _idea_id(artifact_type: str, artifact_id: str, category: str) -> str:
    digest = hashlib.sha256(f"{artifact_type}:{artifact_id}:{category}".encode()).hexdigest()
    return f"content-idea-{category}-{digest[:10]}"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
