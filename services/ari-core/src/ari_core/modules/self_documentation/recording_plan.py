from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from .content_ideas import ContentIdea


@dataclass(frozen=True, slots=True)
class RecordingPlan:
    plan_id: str
    source_idea_id: str
    title: str
    hook: str
    target_platforms: tuple[str, ...]
    recording_format: str
    estimated_duration_seconds: int
    visual_layout: str
    shot_list: tuple[str, ...]
    narration_script: str
    terminal_commands_to_show: tuple[str, ...]
    dashboard_panels_to_show: tuple[str, ...]
    proof_points: tuple[str, ...]
    claims_to_avoid: tuple[str, ...]
    redaction_notes: tuple[str, ...]
    recording_difficulty: str
    edit_complexity: str
    suggested_raw_filename: str
    suggested_export_filename: str
    approval_warning: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def generate_recording_plan_from_idea(idea: ContentIdea) -> RecordingPlan:
    slug = _slug(idea.title)
    return RecordingPlan(
        plan_id=_plan_id(idea.idea_id),
        source_idea_id=idea.idea_id,
        title=idea.title,
        hook=idea.hook,
        target_platforms=idea.platform_fit,
        recording_format=_recording_format(idea.platform_fit),
        estimated_duration_seconds=_duration_seconds(idea.platform_fit),
        visual_layout=_visual_layout(idea),
        shot_list=_shot_list(idea),
        narration_script=_narration_script(idea),
        terminal_commands_to_show=_terminal_commands(idea),
        dashboard_panels_to_show=_dashboard_panels(idea),
        proof_points=idea.proof_points,
        claims_to_avoid=idea.claims_to_avoid,
        redaction_notes=idea.redaction_notes,
        recording_difficulty=idea.recording_difficulty,
        edit_complexity=idea.edit_complexity,
        suggested_raw_filename=f"ari-{slug}-raw.mov",
        suggested_export_filename=f"ari-{slug}-final.mp4",
        approval_warning=(
            "This is a read-only manual recording plan. ARI must not record, edit, "
            "generate audio, upload, publish, or expose sensitive data without "
            "explicit user approval."
        ),
        created_at=_now_iso(),
    )


def _recording_format(platforms: tuple[str, ...]) -> str:
    normalized = " ".join(platforms).lower()
    if "tiktok" in normalized or "reel" in normalized or "short" in normalized:
        if "linkedin" in normalized or "long-form" in normalized:
            return "both"
        return "vertical"
    return "horizontal"


def _duration_seconds(platforms: tuple[str, ...]) -> int:
    normalized = " ".join(platforms).lower()
    if "long-form" in normalized:
        return 90
    if "linkedin" in normalized and ("tiktok" in normalized or "reel" in normalized):
        return 60
    return 45


def _visual_layout(idea: ContentIdea) -> str:
    format_hint = _recording_format(idea.platform_fit)
    if format_hint == "vertical":
        frame = "Use a 9:16 vertical canvas with terminal/dashboard crop centered."
    elif format_hint == "horizontal":
        frame = "Use a 16:9 horizontal canvas with dashboard and terminal side by side."
    else:
        frame = "Capture in 16:9 with enough padding to crop a 9:16 vertical version."
    return (
        f"{frame} Keep ARI/ACE labels visible, show read-only state clearly, "
        f"and follow this visual plan: {idea.visual_plan}"
    )


def _shot_list(idea: ContentIdea) -> tuple[str, ...]:
    shots = [
        f"Cold open: {idea.hook}",
        f"Show the ARI-owned idea/source ids: {', '.join(idea.source_artifact_ids)}.",
        *idea.suggested_shot_list,
        "Show proof points and claims-to-avoid before any public recording.",
        "End on the manual approval boundary: recording/editing/publishing stay disabled.",
    ]
    return tuple(dict.fromkeys(shot for shot in shots if shot.strip()))


def _narration_script(idea: ContentIdea) -> str:
    proof_sentence = " ".join(idea.proof_points[:2])
    return "\n".join(
        (
            idea.hook,
            idea.script_angle,
            f"The evidence is concrete: {proof_sentence}",
            (
                "The important boundary is that ARI owns the truth, while ACE only "
                "displays read-only state."
            ),
            "This is a manual recording plan, not automated publishing.",
        )
    )


def _terminal_commands(idea: ContentIdea) -> tuple[str, ...]:
    commands = ["api self-doc ideas list --json"]
    text = " ".join((idea.title, idea.visual_plan, idea.script_angle)).lower()
    if "content" in text or "self-documentation" in text:
        commands.append("api overview self-documentation --json")
        commands.append("api overview content-ideas --json")
    if "dashboard" in text or "ace" in text:
        commands.append("api overview show --json")
    if "approval" in text or "authority" in text:
        commands.append("api overview pending-approvals --json")
    if "chain" in text or "coding-loop" in text:
        commands.append("api overview coding-loop-chains --json")
    if "lesson" in text or "memory" in text:
        commands.append("api overview lifecycle-lessons --json")
    return tuple(dict.fromkeys(commands))


def _dashboard_panels(idea: ContentIdea) -> tuple[str, ...]:
    panels = ["Content ideas", "Self-documentation artifacts"]
    text = " ".join((idea.title, idea.visual_plan, idea.script_angle)).lower()
    if "dashboard" in text or "ace" in text:
        panels.append("Overview")
    if "approval" in text or "authority" in text:
        panels.append("Pending retry approvals")
    if "chain" in text or "coding-loop" in text:
        panels.append("Recent coding-loop chains")
    if "lesson" in text or "memory" in text:
        panels.append("Lifecycle lessons")
    return tuple(dict.fromkeys(panels))


def _plan_id(idea_id: str) -> str:
    digest = hashlib.sha256(f"recording_plan:{idea_id}".encode()).hexdigest()
    return f"recording-plan-{digest[:12]}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "content-idea"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
