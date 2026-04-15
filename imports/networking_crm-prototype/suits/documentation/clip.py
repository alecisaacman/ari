import argparse
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .demo import _sanitize_save_name
from ...core.paths import DB_PATH


def _clip_artifact_slug(source_video: Path, save_name: Optional[str] = None) -> str:
    if save_name:
        return _sanitize_save_name(save_name)

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", source_video.stem.strip().lower()).strip("-._")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned[:64] or "clip"


def _clip_output_paths(
    source_video: Path,
    *,
    save_name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> tuple[Path, Path]:
    now_value = now or datetime.now()
    output_dir = Path.home() / "ARI" / "clips" / now_value.strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{now_value.strftime('%H%M%S')}-{_clip_artifact_slug(source_video, save_name)}"
    return output_dir / f"{base_name}.mov", output_dir / f"{base_name}.txt"


def _write_clip_metadata(
    metadata_path: Path,
    *,
    timestamp: datetime,
    source_video_path: Path,
    output_clip_path: Path,
    mode: str,
    trim_start: float,
    trim_end: float,
    status: str,
    notes: str,
) -> Path:
    lines = [
        f"timestamp: {timestamp.isoformat(timespec='seconds')}",
        f"source video path: {source_video_path}",
        f"output clip path: {output_clip_path}",
        f"mode: {mode}",
        f"trim-start: {trim_start}",
        f"trim-end: {trim_end}",
        f"status: {status}",
        f"notes: {notes}",
    ]
    metadata_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return metadata_path


def _format_clip_summary(source_video: Path, status: str, clip_path: Path, metadata_path: Path) -> str:
    return "\n".join(
        [
            "CLIP BUILD",
            "",
            f"Source: {source_video}",
            f"Status: {status}",
            f"Clip: {clip_path}",
            f"Metadata: {metadata_path}",
        ]
    )


def _parse_execution_metadata(metadata_path: Path) -> dict[str, Any]:
    if not metadata_path.exists():
        return {}

    parsed: dict[str, Any] = {}
    for raw_line in metadata_path.read_text(encoding="utf-8").splitlines():
        if ": " not in raw_line:
            continue
        key, value = raw_line.split(": ", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _source_metadata_path(source_video: Path) -> Path:
    return source_video.with_suffix(".txt")


def _approximate_proof_trim(duration: float, metadata: dict[str, Any]) -> Optional[tuple[float, float]]:
    try:
        pre_delay = float(metadata.get("pre-delay", "0") or 0)
        post_delay = float(metadata.get("post-delay", "0") or 0)
        proof_line_index = int(metadata.get("proof_line_index", "-1") or -1)
        total_lines = int(metadata.get("total_lines", "0") or 0)
    except (TypeError, ValueError):
        return None

    execution_window = duration - pre_delay - post_delay
    if execution_window <= 0:
        return None

    if total_lines > 0 and proof_line_index >= 0:
        progress = min(max((proof_line_index + 1) / total_lines, 0.0), 1.0)
        proof_time = pre_delay + (execution_window * progress)
        start_time = max(0.0, proof_time - 1.5)
        end_time = min(duration, proof_time + 1.5)
        if end_time > start_time:
            return start_time, end_time

    fallback_start = max(0.0, duration * 0.6 - 1.5)
    fallback_end = duration
    if fallback_end > fallback_start:
        return fallback_start, fallback_end
    return None


def _resolve_clip_window(
    *,
    duration: float,
    mode: str,
    trim_start: float,
    trim_end: float,
    source_video: Path,
) -> tuple[float, float, Optional[dict[str, Any]]]:
    if mode != "proof":
        clip_duration = _validate_clip_request(source_video, trim_start, trim_end, duration)
        return trim_start, clip_duration, None

    metadata = _parse_execution_metadata(_source_metadata_path(source_video))
    if not metadata:
        clip_duration = _validate_clip_request(source_video, trim_start, trim_end, duration)
        return trim_start, clip_duration, None

    proof_window = _approximate_proof_trim(duration, metadata)
    if proof_window is None:
        clip_duration = _validate_clip_request(source_video, trim_start, trim_end, duration)
        return trim_start, clip_duration, None

    start_time, end_time = proof_window
    return start_time, end_time - start_time, metadata


def _failure_guidance(
    notes: str,
    source_video: Path,
    metadata_path: Optional[Path],
    clip_path: Optional[Path] = None,
) -> str:
    reason = notes.strip() or "Clip build failed."
    next_step = "review the error details and rerun the clip build command"

    if "ffmpeg is not installed" in reason:
        reason = "ffmpeg is not installed"
        next_step = "brew install ffmpeg"
    elif "Source video not found" in reason:
        next_step = "verify the raw video artifact exists at the source path"
    elif "Trim values remove the full video duration" in reason or "trim-start and trim-end must be non-negative" in reason:
        if "non-negative" in reason:
            reason = "trim-start and trim-end must be non-negative"
        else:
            reason = "the requested trims remove the whole video"
        next_step = "lower trim-start / trim-end and rerun the clip build command"

    lines = [
        "CLIP BUILD",
        "",
        f"Source: {source_video}",
        "Status: FAILED",
        f"Reason: {reason}",
        "",
        "Next step:",
        f"  {next_step}",
    ]

    rerun_save_name: Optional[str] = None
    if clip_path is not None:
        rerun_save_name = re.sub(r"^\d{6}-", "", clip_path.stem)

    if "ffmpeg is not installed" in reason:
        lines.extend(
            [
                "",
                "Then rerun:",
                (
                    f"  ari docs clip build --video \"{source_video}\" --save-name {rerun_save_name}"
                    if rerun_save_name
                    else f"  ari docs clip build --video \"{source_video}\""
                ),
            ]
        )
    elif "Source video not found" in notes or "trim" in reason:
        lines.extend(
            [
                "",
                "Then rerun:",
                f"  ari docs clip build --video \"{source_video}\"",
            ]
        )

    lines.extend(
        [
            "",
            "Metadata saved:" if metadata_path is not None else "Metadata unavailable:",
            f"  {metadata_path}" if metadata_path is not None else "  [unavailable]",
        ]
    )
    return "\n".join(lines)


def _format_clip_result(result: dict[str, object]) -> str:
    source_video = result["source_video"]
    status = result["status"]
    clip_path = result["clip_path"]
    metadata_path = result["metadata_path"]
    notes = str(result["notes"])
    mode = str(result.get("mode", "default"))

    if status == "SUCCESS":
        if mode == "proof":
            proof_line = str(result.get("proof_line", "")).strip() or "[unavailable]"
            return "\n".join(
                [
                    "CLIP BUILD",
                    "",
                    "Mode: PROOF-AWARE",
                    "Detected proof:",
                    f'  "{proof_line}"',
                    "",
                    "Segment:",
                    "  capturing final execution moment",
                    "",
                    "Clip:",
                    f"  {clip_path}",
                    "",
                    "Next step:",
                    "  review whether this moment clearly demonstrates the feature",
                    "",
                    f"Source: {source_video}",
                    f"Status: {status}",
                    f"Metadata: {metadata_path}",
                ]
            )
        return "\n".join(
            [
                "CLIP BUILD",
                "",
                f"Source: {source_video}",
                f"Status: {status}",
                f"Clip: {clip_path}",
                f"Metadata: {metadata_path}",
                "",
                "Next step:",
                "  review the clip and decide whether to extract a proof moment or format for vertical video",
            ]
        )

    return _failure_guidance(notes, source_video, metadata_path, clip_path)


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def _parse_ffmpeg_duration(stderr_text: str) -> Optional[float]:
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr_text)
    if not match:
        return None

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def _probe_video_duration(source_video: Path) -> float:
    if _ffprobe_available():
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(source_video),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            duration_text = result.stdout.strip()
            if duration_text:
                try:
                    return float(duration_text)
                except ValueError:
                    pass
        raise RuntimeError("Unable to determine video duration with ffprobe.")

    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg is not installed. Install ffmpeg to build clips.")

    result = subprocess.run(
        ["ffmpeg", "-i", str(source_video)],
        capture_output=True,
        text=True,
        check=False,
    )
    duration = _parse_ffmpeg_duration(result.stderr)
    if duration is None:
        raise RuntimeError("Unable to determine video duration reliably with ffmpeg.")
    return duration


def _validate_clip_request(source_video: Path, trim_start: float, trim_end: float, duration: float) -> float:
    if trim_start < 0 or trim_end < 0:
        raise ValueError("trim-start and trim-end must be non-negative.")

    clip_duration = duration - trim_start - trim_end
    if clip_duration <= 0:
        raise ValueError("Trim values remove the full video duration.")
    return clip_duration


def _run_clip_command(source_video: Path, output_clip_path: Path, trim_start: float, clip_duration: float) -> None:
    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg is not installed. Install ffmpeg to build clips.")

    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{trim_start}",
            "-i",
            str(source_video),
            "-t",
            f"{clip_duration}",
            "-c",
            "copy",
            str(output_clip_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        notes = result.stderr.strip() or result.stdout.strip() or "ffmpeg clip build failed."
        raise RuntimeError(notes)


def build_clip(
    source_video: str,
    *,
    save_name: Optional[str] = None,
    mode: str = "default",
    trim_start: float = 0.5,
    trim_end: float = 0.5,
    now: Optional[datetime] = None,
) -> dict[str, object]:
    timestamp = now or datetime.now()
    source_path = Path(source_video).expanduser()
    output_clip_path, metadata_path = _clip_output_paths(source_path, save_name=save_name, now=timestamp)

    status = "FAILED"
    notes = "Clip build did not start."
    exit_code = 1
    proof_line = ""

    try:
        if trim_start < 0 or trim_end < 0:
            raise ValueError("trim-start and trim-end must be non-negative.")
        if not source_path.exists():
            raise FileNotFoundError(f"Source video not found: {source_path}")
        duration = _probe_video_duration(source_path)
        resolved_trim_start, clip_duration, metadata = _resolve_clip_window(
            duration=duration,
            mode=mode,
            trim_start=trim_start,
            trim_end=trim_end,
            source_video=source_path,
        )
        if metadata:
            proof_line = str(metadata.get("proof_line", ""))
        resolved_trim_end = max(0.0, duration - resolved_trim_start - clip_duration)
        _run_clip_command(source_path, output_clip_path, resolved_trim_start, clip_duration)
        status = "SUCCESS"
        notes = "Clip built successfully with ffmpeg."
        exit_code = 0
    except Exception as exc:
        notes = str(exc)
        resolved_trim_start = trim_start
        resolved_trim_end = trim_end

    _write_clip_metadata(
        metadata_path,
        timestamp=timestamp,
        source_video_path=source_path,
        output_clip_path=output_clip_path,
        mode=mode,
        trim_start=resolved_trim_start,
        trim_end=resolved_trim_end,
        status=status,
        notes=notes,
    )

    return {
        "status": status,
        "exit_code": exit_code,
        "source_video": source_path,
        "clip_path": output_clip_path,
        "metadata_path": metadata_path,
        "notes": notes,
        "mode": mode,
        "proof_line": proof_line,
    }


def handle_clip_build(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    del db_path
    try:
        result = build_clip(
            args.video,
            save_name=getattr(args, "save_name", None),
            mode=getattr(args, "mode", "default"),
            trim_start=getattr(args, "trim_start", 0.5),
            trim_end=getattr(args, "trim_end", 0.5),
        )
    except Exception as exc:
        source_path = Path(args.video).expanduser()
        print(_failure_guidance(str(exc), source_path, None))
        return 1

    print(_format_clip_result(result))
    return int(result["exit_code"])
