from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from ari_core.core.paths import DB_PATH
from ari_core.modules.self_documentation import (
    ContentPackage,
    ContentSeed,
    list_content_packages,
    list_content_seeds,
)


@dataclass(frozen=True, slots=True)
class SelfDocumentationArtifactSummary:
    artifact_id: str
    artifact_type: str
    title: str
    summary: str
    source_commit_range: str | None
    source_seed_id: str | None
    proof_point_count: int
    visual_moment_count: int
    redaction_note_count: int
    claims_to_avoid_count: int
    has_voiceover_draft: bool
    has_shot_list: bool
    has_terminal_demo_plan: bool
    has_caption: bool
    created_at: str
    inspection_hint: str
    readiness_status: str


@dataclass(frozen=True, slots=True)
class SelfDocumentationReadModel:
    generated_at: str
    total_seed_count: int
    total_package_count: int
    recent_artifacts: tuple[SelfDocumentationArtifactSummary, ...]
    unavailable_reason: str | None
    source_of_truth: str
    authority_warning: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_self_documentation_read_model(
    *,
    db_path: Path = DB_PATH,
    limit: int = 20,
) -> SelfDocumentationReadModel:
    source_of_truth = "durable self-documentation ContentSeed and ContentPackage storage"
    authority_warning = (
        "This read model is inspection-only. ACE may display self-documentation "
        "artifacts but must not generate content, mutate artifacts, record, edit, "
        "upload, publish, or own content truth."
    )
    try:
        seeds = list_content_seeds(limit=limit, db_path=db_path)
        packages = list_content_packages(limit=limit, db_path=db_path)
    except Exception as error:  # pragma: no cover - exercised through monkeypatch tests.
        return SelfDocumentationReadModel(
            generated_at=_now_iso(),
            total_seed_count=0,
            total_package_count=0,
            recent_artifacts=(),
            unavailable_reason=(
                "Self-documentation artifacts are unavailable: "
                f"{type(error).__name__}: {error}"
            ),
            source_of_truth=source_of_truth,
            authority_warning=authority_warning,
        )

    summaries = tuple(
        sorted(
            (
                *(_summarize_seed(seed) for seed in seeds),
                *(_summarize_package(package) for package in packages),
            ),
            key=lambda artifact: artifact.created_at,
            reverse=True,
        )[:limit]
    )
    return SelfDocumentationReadModel(
        generated_at=_now_iso(),
        total_seed_count=len(seeds),
        total_package_count=len(packages),
        recent_artifacts=summaries,
        unavailable_reason=None,
        source_of_truth=source_of_truth,
        authority_warning=authority_warning,
    )


def _summarize_seed(seed: ContentSeed) -> SelfDocumentationArtifactSummary:
    return SelfDocumentationArtifactSummary(
        artifact_id=seed.seed_id,
        artifact_type="content_seed",
        title=seed.title,
        summary=seed.one_sentence_summary,
        source_commit_range=seed.source_commit_range,
        source_seed_id=None,
        proof_point_count=len(seed.proof_points),
        visual_moment_count=len(seed.visual_moments),
        redaction_note_count=len(seed.redaction_notes),
        claims_to_avoid_count=len(seed.claims_to_avoid),
        has_voiceover_draft=bool(seed.suggested_voiceover.strip()),
        has_shot_list=False,
        has_terminal_demo_plan=False,
        has_caption=bool(seed.suggested_short_caption.strip()),
        created_at=seed.created_at,
        inspection_hint=f"api self-doc seeds show --id {seed.seed_id}",
        readiness_status=_readiness_status(
            has_required_content=bool(seed.proof_points and seed.title.strip()),
            risk_text=(*seed.risk_notes, *seed.redaction_notes, *seed.claims_to_avoid),
        ),
    )


def _summarize_package(package: ContentPackage) -> SelfDocumentationArtifactSummary:
    return SelfDocumentationArtifactSummary(
        artifact_id=package.package_id,
        artifact_type="content_package",
        title=package.title,
        summary=package.content_angle,
        source_commit_range=None,
        source_seed_id=package.source_seed_id,
        proof_point_count=0,
        visual_moment_count=len(package.shot_list),
        redaction_note_count=len(package.redaction_checklist),
        claims_to_avoid_count=len(package.claims_to_avoid),
        has_voiceover_draft=bool(package.voiceover_draft.strip()),
        has_shot_list=bool(package.shot_list),
        has_terminal_demo_plan=bool(package.terminal_demo_plan),
        has_caption=bool(package.short_caption.strip()),
        created_at=package.created_at,
        inspection_hint=f"api self-doc packages show --id {package.package_id}",
        readiness_status=_readiness_status(
            has_required_content=bool(
                package.shot_list
                and package.terminal_demo_plan
                and package.title.strip()
                and package.short_caption.strip()
            ),
            risk_text=(*package.redaction_checklist, *package.claims_to_avoid),
        ),
    )


def _readiness_status(
    *,
    has_required_content: bool,
    risk_text: tuple[str, ...],
) -> str:
    if not has_required_content:
        return "partial"
    if _has_sensitive_redaction_signal(risk_text):
        return "needs_redaction_review"
    return "ready_for_review"


def _has_sensitive_redaction_signal(values: tuple[str, ...]) -> bool:
    haystack = " ".join(values).lower()
    sensitive_terms = (
        "api key-like",
        "secret-like",
        ".env reference",
        "private absolute path",
        "email address",
        "review and redact",
        "token detected",
        "credential",
        "password",
    )
    return any(term in haystack for term in sensitive_terms)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
