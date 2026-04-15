import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ...core.paths import DB_PATH
from .storyboard import _sanitize_filename_part, build_short_video_storyboard_data


def _recording_goal(topic: str, demo_metadata: dict[str, str]) -> str:
    if demo_metadata.get("what_it_shows"):
        return f"Record a short piece that shows {demo_metadata['what_it_shows']} and makes the workflow easy to explain."
    return f"Record a short piece that shows how {topic.strip()} turns into a concrete ARI workflow."


def _assets(topic: str, demo_metadata: dict[str, str]) -> List[str]:
    assets = [
        "terminal open in the project folder",
        "recording window framed so the prompt and output are readable",
        "quiet room and mic ready",
        "camera optional for hook and close",
    ]
    command = demo_metadata.get("command")
    if command:
        assets.insert(1, f"exact demo command ready: `{command}`")
        assets.insert(2, "saved demo artifact available for reference")
    else:
        assets.insert(1, f"one relevant ARI command ready for {topic.strip()}")
    return assets


def _recording_steps(topic: str, storyboard_data: dict[str, object]) -> List[str]:
    beats = storyboard_data["beats"]
    demo_metadata = storyboard_data["demo_metadata"]
    command = demo_metadata.get("command")
    setup_command = f"Put `{command}` at the prompt." if command else f"Put a relevant ARI command for {topic.strip()} at the prompt."
    run_command = f"Run `{command}` once the hook lands." if command else "Run the command as the proof/demo moment."
    proof_step = (
        f"Pause on the output that proves {demo_metadata.get('what_it_shows', 'the result')}."
        if command
        else "Pause on the most important output line and keep it readable for a beat."
    )
    close_reference = beats[-1]["spoken"] if beats else "Deliver the close cleanly."

    return [
        "Open terminal in the project root and clear visual clutter.",
        setup_command,
        "Start screen recording, and start camera recording too if you want a talking-head hook.",
        f"Deliver the hook out loud: {storyboard_data['hook']}",
        run_command,
        proof_step,
        f"Record the close while holding the final frame: {close_reference}",
        "Stop recording only after a one-second still hold on the final frame.",
    ]


def _shot_timing(storyboard_data: dict[str, object]) -> List[str]:
    beats = storyboard_data["beats"]
    proof_end = 22 if len(beats) > 7 else 20
    close_end = 30 if len(beats) > 6 else 28
    return [
        "hook: 0-3 sec",
        "setup: 3-8 sec",
        f"proof/demo: 8-{proof_end} sec",
        f"close: {proof_end}-{close_end} sec",
    ]


def _on_screen_text(topic: str, storyboard_data: dict[str, object]) -> List[str]:
    demo_metadata = storyboard_data["demo_metadata"]
    overlays = [
        topic.strip(),
        "Real local workflow",
    ]
    if demo_metadata.get("what_it_shows"):
        overlays.append(demo_metadata["what_it_shows"])
    else:
        overlays.append("Thin bridge from plan to capture")
    if demo_metadata.get("suggested_caption"):
        overlays.append(demo_metadata["suggested_caption"])
    else:
        overlays.append("Keep the proof moment on screen")
    return overlays[:4]


def _notes(storyboard_data: dict[str, object]) -> List[str]:
    demo_metadata = storyboard_data["demo_metadata"]
    notes = [
        "Keep the cursor visible during setup and execution.",
        "Avoid scrolling during the proof moment unless one line clearly needs a punch-in.",
        "Leave a short silent buffer before and after each spoken segment for easier editing later.",
    ]
    if demo_metadata.get("command"):
        notes.append("Use the saved demo artifact as reference so the live take matches the command and proof beat.")
    else:
        notes.append("Choose one command and one output line before recording so the take stays tight.")
    return notes


def generate_recording_plan(
    topic: str,
    style: str = "balanced",
    demo_file: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> str:
    storyboard_data = build_short_video_storyboard_data(
        topic=topic,
        style=style,
        demo_file=demo_file,
        db_path=db_path,
    )
    demo_metadata = storyboard_data["demo_metadata"]

    lines = [
        "TITLE",
        f"- {storyboard_data['title']}",
        "",
        "RECORDING GOAL",
        f"- {_recording_goal(topic, demo_metadata)}",
        "",
        "ASSETS",
    ]
    for asset in _assets(topic, demo_metadata):
        lines.append(f"- {asset}")

    lines.extend(["", "RECORDING STEPS"])
    for index, step in enumerate(_recording_steps(topic, storyboard_data), start=1):
        lines.append(f"{index}. {step}")

    lines.extend(["", "SHOT TIMING"])
    for item in _shot_timing(storyboard_data):
        lines.append(f"- {item}")

    lines.extend(["", "ON-SCREEN TEXT"])
    for overlay in _on_screen_text(topic, storyboard_data):
        lines.append(f"- {overlay}")

    lines.extend(["", "NOTES"])
    for note in _notes(storyboard_data):
        lines.append(f"- {note}")

    return "\n".join(lines)


def _save_recording_plan(plan: str, topic: str, now: Optional[datetime] = None) -> Path:
    now_value = now or datetime.now()
    output_dir = Path.home() / "ARI" / "recordings" / now_value.strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{now_value.strftime('%H%M%S')}-{_sanitize_filename_part(topic)[:48]}.txt"
    output_path = output_dir / filename
    output_path.write_text(plan + "\n", encoding="utf-8")
    return output_path


def handle_record_plan(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    plan = generate_recording_plan(
        topic=args.topic,
        style=getattr(args, "style", "balanced") or "balanced",
        demo_file=getattr(args, "demo_file", None),
        db_path=db_path,
    )
    print(plan)
    if getattr(args, "save", False):
        _save_recording_plan(plan=plan, topic=args.topic)
    return 0
