from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from .content_seed import ContentSeed


@dataclass(frozen=True, slots=True)
class Shot:
    label: str
    purpose: str
    suggested_visual: str
    narration: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DemoStep:
    command_or_action: str
    purpose: str
    expected_result: str
    safety_note: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ContentPackage:
    package_id: str
    source_seed_id: str
    title: str
    content_angle: str
    thirty_second_vertical_script: str
    sixty_second_linkedin_script: str
    shot_list: tuple[Shot, ...]
    terminal_demo_plan: tuple[DemoStep, ...]
    voiceover_draft: str
    linkedin_post: str
    short_caption: str
    thumbnail_prompt: str
    redaction_checklist: tuple[str, ...]
    claims_to_avoid: tuple[str, ...]
    approval_required_before_recording: bool
    approval_required_before_posting: bool
    created_at: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["shot_list"] = [shot.to_dict() for shot in self.shot_list]
        payload["terminal_demo_plan"] = [step.to_dict() for step in self.terminal_demo_plan]
        return payload


def generate_content_package_from_seed(seed: ContentSeed) -> ContentPackage:
    proof_points = _select_proof_points(seed)
    content_angle = seed.next_content_angle or seed.demo_idea
    return ContentPackage(
        package_id=f"content-package-{uuid4()}",
        source_seed_id=seed.seed_id,
        title=seed.title,
        content_angle=content_angle,
        thirty_second_vertical_script=_vertical_script(seed, proof_points),
        sixty_second_linkedin_script=_linkedin_script(seed, proof_points),
        shot_list=_shot_list(seed, proof_points),
        terminal_demo_plan=_terminal_demo_plan(seed),
        voiceover_draft=seed.suggested_voiceover,
        linkedin_post=seed.suggested_linkedin_post,
        short_caption=seed.suggested_short_caption,
        thumbnail_prompt=_thumbnail_prompt(seed),
        redaction_checklist=_redaction_checklist(seed),
        claims_to_avoid=tuple(seed.claims_to_avoid),
        approval_required_before_recording=True,
        approval_required_before_posting=True,
    )


def content_package_from_dict(payload: Mapping[str, object]) -> ContentPackage:
    return ContentPackage(
        package_id=_required_str(payload, "package_id"),
        source_seed_id=_required_str(payload, "source_seed_id"),
        title=_required_str(payload, "title"),
        content_angle=_required_str(payload, "content_angle"),
        thirty_second_vertical_script=_required_str(
            payload, "thirty_second_vertical_script"
        ),
        sixty_second_linkedin_script=_required_str(
            payload, "sixty_second_linkedin_script"
        ),
        shot_list=tuple(_shot_from_dict(shot) for shot in _required_sequence(payload, "shot_list")),
        terminal_demo_plan=tuple(
            _demo_step_from_dict(step)
            for step in _required_sequence(payload, "terminal_demo_plan")
        ),
        voiceover_draft=_required_str(payload, "voiceover_draft"),
        linkedin_post=_required_str(payload, "linkedin_post"),
        short_caption=_required_str(payload, "short_caption"),
        thumbnail_prompt=_required_str(payload, "thumbnail_prompt"),
        redaction_checklist=_required_str_tuple(payload, "redaction_checklist"),
        claims_to_avoid=_required_str_tuple(payload, "claims_to_avoid"),
        approval_required_before_recording=_required_bool(
            payload, "approval_required_before_recording"
        ),
        approval_required_before_posting=_required_bool(
            payload, "approval_required_before_posting"
        ),
        created_at=_required_str(payload, "created_at"),
    )


def _shot_from_dict(payload: object) -> Shot:
    if not isinstance(payload, Mapping):
        raise ValueError("shot_list must contain objects.")
    return Shot(
        label=_required_str(payload, "label"),
        purpose=_required_str(payload, "purpose"),
        suggested_visual=_required_str(payload, "suggested_visual"),
        narration=_required_str(payload, "narration"),
    )


def _demo_step_from_dict(payload: object) -> DemoStep:
    if not isinstance(payload, Mapping):
        raise ValueError("terminal_demo_plan must contain objects.")
    return DemoStep(
        command_or_action=_required_str(payload, "command_or_action"),
        purpose=_required_str(payload, "purpose"),
        expected_result=_required_str(payload, "expected_result"),
        safety_note=_required_str(payload, "safety_note"),
    )


def _required_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"ContentPackage field {key!r} is required and must be a string.")
    return value


def _required_bool(payload: Mapping[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"ContentPackage field {key!r} is required and must be a bool.")
    return value


def _required_sequence(payload: Mapping[str, object], key: str) -> tuple[object, ...]:
    value = payload.get(key)
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"ContentPackage field {key!r} is required and must be a list.")
    return tuple(value)


def _required_str_tuple(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    values = _required_sequence(payload, key)
    if not all(isinstance(value, str) for value in values):
        raise ValueError(f"ContentPackage field {key!r} must contain only strings.")
    return tuple(values)


def _select_proof_points(seed: ContentSeed) -> tuple[str, ...]:
    return tuple(seed.proof_points[:3]) or (
        "No proof points were supplied; keep this package internal until evidence exists.",
    )


def _vertical_script(seed: ContentSeed, proof_points: tuple[str, ...]) -> str:
    proof = proof_points[0]
    hook = seed.hook_options[0] if seed.hook_options else seed.title
    return (
        f"{hook}\n\n"
        f"{seed.one_sentence_summary}\n\n"
        f"Why it matters: {seed.why_it_matters}\n\n"
        f"Proof: {proof}\n\n"
        "Boundary: this is a content package only. It does not record, publish, "
        "or claim capabilities beyond the seed evidence."
    )


def _linkedin_script(seed: ContentSeed, proof_points: tuple[str, ...]) -> str:
    proof_lines = "\n".join(f"- {point}" for point in proof_points)
    return (
        f"{seed.title}\n\n"
        f"{seed.one_sentence_summary}\n\n"
        f"{seed.why_it_matters}\n\n"
        f"Evidence:\n{proof_lines}\n\n"
        f"Demo angle: {seed.demo_idea}\n\n"
        "The important boundary: this is grounded content planning, not recording, "
        "editing, uploading, or publishing."
    )


def _shot_list(seed: ContentSeed, proof_points: tuple[str, ...]) -> tuple[Shot, ...]:
    first_visual = (
        seed.visual_moments[0]
        if seed.visual_moments
        else "Show the source commits and changed files."
    )
    return (
        Shot(
            label="Evidence",
            purpose="Ground the package in real ARI activity.",
            suggested_visual=first_visual,
            narration=proof_points[0],
        ),
        Shot(
            label="Why It Matters",
            purpose="Explain the product value without exaggeration.",
            suggested_visual=seed.demo_idea,
            narration=seed.why_it_matters,
        ),
        Shot(
            label="Boundary",
            purpose="Show what ARI still does not do in this slice.",
            suggested_visual="Show claims_to_avoid and approval requirements.",
            narration="Recording and posting require approval and are not part of this package.",
        ),
    )


def _terminal_demo_plan(seed: ContentSeed) -> tuple[DemoStep, ...]:
    source_range = seed.source_commit_range or "<commit-range>"
    return (
        DemoStep(
            command_or_action=(
                "api self-doc seed from-commits "
                f"--from {source_range.split('..', maxsplit=1)[0]} "
                f"--to {_range_end(source_range)} --json"
            ),
            purpose="Regenerate the grounded source ContentSeed.",
            expected_result=(
                "JSON output includes seed_id, source commits, files, and proof points."
            ),
            safety_note="Read-only local git inspection; no persistence or external service call.",
        ),
        DemoStep(
            command_or_action="Inspect generated package fields.",
            purpose=(
                "Review scripts, shot list, demo plan, redaction checklist, and claims to avoid."
            ),
            expected_result="A deterministic content plan derived from the seed evidence.",
            safety_note="Do not record, export, upload, or post without explicit approval.",
        ),
    )


def _range_end(source_range: str) -> str:
    if ".." not in source_range:
        return "<to-ref>"
    return source_range.split("..", maxsplit=1)[1]


def _thumbnail_prompt(seed: ContentSeed) -> str:
    return (
        f"Create a clean terminal/product thumbnail for '{seed.title}'. "
        "Show evidence-backed ARI self-documentation, avoid logos, secrets, private paths, "
        "or claims of recording/publishing automation."
    )


def _redaction_checklist(seed: ContentSeed) -> tuple[str, ...]:
    checklist = [
        "Confirm no API keys, tokens, credentials, or environment variables are visible.",
        "Confirm no private absolute paths, emails, or personal data are visible.",
        "Confirm every capability claim is supported by the source seed evidence.",
        "Confirm recording, export, upload, and posting remain approval-gated.",
        "Review source seed redaction notes before public use.",
    ]
    if seed.redaction_notes:
        checklist.extend(seed.redaction_notes)
    if seed.risk_notes:
        checklist.extend(seed.risk_notes)
    return tuple(dict.fromkeys(checklist))


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
