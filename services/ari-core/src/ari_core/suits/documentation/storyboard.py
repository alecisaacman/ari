import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ...core.paths import DB_PATH
from .content import generate_short_video_script


def _sanitize_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return cleaned or "storyboard"


def _expand_path(path_value: str) -> Path:
    return Path(path_value).expanduser()


def _parse_script_sections(script: str) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {}
    current_label: Optional[str] = None
    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.isupper():
            current_label = line
            sections[current_label] = []
            continue
        if current_label is not None:
            sections[current_label].append(line)
    return sections


def _read_demo_metadata(demo_file: Optional[str]) -> Dict[str, str]:
    if not demo_file:
        return {}

    artifact_path = _expand_path(demo_file)
    content = artifact_path.read_text(encoding="utf-8")
    metadata: Dict[str, str] = {"artifact_path": str(artifact_path)}
    for line in content.splitlines():
        if line.startswith("Demo command: "):
            metadata["command"] = line.removeprefix("Demo command: ").strip()
        elif line.startswith("What it shows: "):
            metadata["what_it_shows"] = line.removeprefix("What it shows: ").strip()
        elif line.startswith("Suggested caption: "):
            metadata["suggested_caption"] = line.removeprefix("Suggested caption: ").strip()
    return metadata


def _title_for(topic: str, style: str, demo_metadata: Dict[str, str]) -> str:
    style_label = "balanced" if style == "balanced" else style
    if demo_metadata.get("command"):
        return f"{topic.strip()} | {style_label} short with live demo"
    return f"{topic.strip()} | {style_label} short storyboard"


def _beat(beat_number: int, visual: str, spoken: str, notes: str) -> str:
    return "\n".join(
        [
            f"Beat {beat_number}",
            f"Visual: {visual}",
            f"Spoken: {spoken}",
            f"Notes: {notes}",
        ]
    )


def _generic_beat_plan(topic: str, hook_lines: List[str], context_lines: List[str], core_lines: List[str], close_lines: List[str]) -> List[Dict[str, str]]:
    hook_spoken = " ".join(hook_lines[:2]).strip()
    beats = [
        {
            "visual": "cold open on camera, then quick cut to terminal window",
            "spoken": hook_spoken,
            "notes": "start tight; first 2 seconds should move fast",
        },
        {
            "visual": "terminal command prompt visible with ARI workspace open",
            "spoken": context_lines[0] if context_lines else f"I've been building this around {topic}.",
            "notes": "keep cursor visible and frame the terminal cleanly",
        },
        {
            "visual": "type a relevant ARI command or show the command area before execution",
            "spoken": context_lines[1] if len(context_lines) > 1 else f"The system is still thin, but the workflow is already real.",
            "notes": "show intent before showing output",
        },
        {
            "visual": "screen recording of the output arriving, with a slight zoom on the key line",
            "spoken": core_lines[0] if core_lines else "The useful part is keeping the layer small.",
            "notes": "pause long enough for one key line to read",
        },
        {
            "visual": "zoom further into the most important output line or add a text overlay",
            "spoken": core_lines[1] if len(core_lines) > 1 else "It only needs enough structure to hold the point.",
            "notes": "use text overlay for emphasis instead of more screen movement",
        },
        {
            "visual": "cut back to camera or picture-in-picture over the terminal",
            "spoken": core_lines[3] if len(core_lines) > 3 else (core_lines[2] if len(core_lines) > 2 else "That is why this matters."),
            "notes": "deliver this line more directly; let the screen stay stable",
        },
        {
            "visual": "hold on final terminal frame with a short closing overlay",
            "spoken": close_lines[0] if close_lines else "This is the bridge from work into video.",
            "notes": "end on a clean frame that could also work as a thumbnail",
        },
    ]
    return beats


def _apply_demo_enrichment(beats: List[Dict[str, str]], demo_metadata: Dict[str, str]) -> List[Dict[str, str]]:
    command = demo_metadata.get("command")
    if not command:
        return beats

    what_it_shows = demo_metadata.get("what_it_shows", "the live demo output")
    caption = demo_metadata.get("suggested_caption", "")
    artifact_path = demo_metadata.get("artifact_path", "")

    beats[1]["visual"] = f"terminal opens with `{command}` staged at the prompt"
    beats[1]["notes"] = "show the exact command clearly before execution"
    beats[2]["visual"] = f"run `{command}` and keep the first output visible"
    beats[2]["notes"] = f"let the command complete cleanly; this is the proof moment for {what_it_shows}"
    beats[3]["visual"] = f"zoom into the output that shows {what_it_shows}"
    beats[3]["notes"] = "pick one readable line and punch in rather than scrolling"

    insert_index = 5 if len(beats) > 5 else len(beats) - 1
    beats.insert(
        insert_index,
        {
            "visual": f"brief overlay of saved demo artifact or filename `{artifact_path}`",
            "spoken": f"This is already grounded in a real demo capture, not a mockup.",
            "notes": f"use a quick text overlay; optional caption reference: {caption or 'keep it minimal'}",
        },
    )
    return beats[:8]


def build_short_video_storyboard_data(
    topic: str,
    style: str = "balanced",
    demo_file: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> Dict[str, object]:
    style_value = style or "balanced"
    script = generate_short_video_script(topic=topic, style=style_value, db_path=db_path)
    sections = _parse_script_sections(script)
    demo_metadata = _read_demo_metadata(demo_file)

    hook_lines = sections.get("HOOK", [])
    context_lines = sections.get("CONTEXT", [])
    core_lines = sections.get("CORE IDEA", [])
    close_lines = sections.get("CTA / CLOSE", [])

    beats = _generic_beat_plan(topic, hook_lines, context_lines, core_lines, close_lines)
    beats = _apply_demo_enrichment(beats, demo_metadata)
    if len(beats) < 4:
        raise ValueError("Storyboard must contain at least four beats.")

    return {
        "title": _title_for(topic, style_value, demo_metadata),
        "hook": " ".join(hook_lines[:2]).strip(),
        "beats": beats,
        "script": script,
        "sections": sections,
        "demo_metadata": demo_metadata,
    }


def generate_short_video_storyboard(
    topic: str,
    style: str = "balanced",
    demo_file: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> str:
    data = build_short_video_storyboard_data(
        topic=topic,
        style=style,
        demo_file=demo_file,
        db_path=db_path,
    )
    beats = data["beats"]
    demo_metadata = data["demo_metadata"]

    lines = [
        "TITLE",
        f"- {data['title']}",
        "",
        "HOOK",
        f"- {data['hook']}",
        "",
        "SHOT PLAN",
    ]
    for index, beat in enumerate(beats, start=1):
        lines.extend(
            [
                _beat(
                    beat_number=index,
                    visual=beat["visual"],
                    spoken=beat["spoken"],
                    notes=beat["notes"],
                ),
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _save_storyboard(storyboard: str, topic: str, now: Optional[datetime] = None) -> Path:
    now_value = now or datetime.now()
    output_dir = Path.home() / "ARI" / "storyboards" / now_value.strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{now_value.strftime('%H%M%S')}-{_sanitize_filename_part(topic)[:48]}.txt"
    output_path = output_dir / filename
    output_path.write_text(storyboard + "\n", encoding="utf-8")
    return output_path


def handle_storyboard_short_video(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    storyboard = generate_short_video_storyboard(
        topic=args.topic,
        style=getattr(args, "style", "balanced") or "balanced",
        demo_file=getattr(args, "demo_file", None),
        db_path=db_path,
    )
    print(storyboard)
    if getattr(args, "save", False):
        _save_storyboard(storyboard=storyboard, topic=args.topic)
    return 0
