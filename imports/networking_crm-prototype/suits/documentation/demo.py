import argparse
import os
import re
import signal
import subprocess
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...core.paths import DB_PATH


def _sanitize_save_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-._")
    if not cleaned:
        raise ValueError("Save name must include at least one letter or number.")
    return cleaned


def _artifact_slug(command: str, save_name: Optional[str] = None) -> str:
    if save_name:
        return _sanitize_save_name(save_name)

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", command.strip().lower()).strip("-._")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned[:64] or "command"


def _execution_capture_paths(
    command: str,
    save_name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> tuple[Path, Path]:
    now_value = now or datetime.now()
    output_dir = Path.home() / "ARI" / "videos" / now_value.strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{now_value.strftime('%H%M%S')}-{_artifact_slug(command, save_name)}"
    return output_dir / f"{base_name}.mov", output_dir / f"{base_name}.txt"


def detect_proof_line(stdout: str) -> Optional[str]:
    lines = [line.rstrip() for line in stdout.splitlines()]
    non_empty_lines = [line for line in lines if line.strip()]
    if not non_empty_lines:
        return None

    preferred_markers = ("SUCCESS", "Saved:", "Clip:", "Status:")
    for line in reversed(non_empty_lines):
        if any(marker in line for marker in preferred_markers):
            return line

    return non_empty_lines[-1]


def _proof_metadata(stdout: str) -> dict[str, Any]:
    lines = [line.rstrip() for line in stdout.splitlines()]
    total_lines = len(lines)
    proof_line = detect_proof_line(stdout)
    if proof_line is None:
        fallback_lines = [line for line in lines[-3:] if line.strip()]
        proof_line = " | ".join(fallback_lines) if fallback_lines else ""
        proof_line_index = total_lines - 1 if total_lines > 0 else -1
    else:
        proof_line_index = -1
        for index in range(total_lines - 1, -1, -1):
            if lines[index] == proof_line:
                proof_line_index = index
                break

    return {
        "proof_line": proof_line,
        "proof_line_index": proof_line_index,
        "total_lines": total_lines,
    }


def _write_execution_metadata(
    metadata_path: Path,
    *,
    timestamp: datetime,
    command: str,
    pre_delay: float,
    post_delay: float,
    video_path: Path,
    status: str,
    notes: str,
    proof_line: str = "",
    proof_line_index: int = -1,
    total_lines: int = 0,
) -> Path:
    lines = [
        f"timestamp: {timestamp.isoformat(timespec='seconds')}",
        f"command: {command}",
        f"pre-delay: {pre_delay}",
        f"post-delay: {post_delay}",
        f"output video path: {video_path}",
        f"status: {status}",
        f"proof_line: {proof_line}",
        f"proof_line_index: {proof_line_index}",
        f"total_lines: {total_lines}",
        f"notes: {notes}",
    ]
    metadata_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return metadata_path


def _format_execution_summary(command: str, status: str, video_path: Path, metadata_path: Path) -> str:
    return "\n".join(
        [
            "EXECUTION CAPTURE",
            f"Command: {command}",
            f"Status: {status}",
            f"Video: {video_path}",
            f"Metadata: {metadata_path}",
        ]
    )


def _start_screen_recording(video_path: Path) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        ["/usr/sbin/screencapture", "-v", "-x", str(video_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.5)
    if process.poll() is not None:
        stderr = ""
        if process.stderr is not None:
            stderr = process.stderr.read().strip()
        raise RuntimeError(stderr or "screencapture exited before recording began.")
    return process


def _stop_screen_recording(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait(timeout=5)
        raise RuntimeError("Timed out while stopping the screen recording.") from exc

    if process.returncode not in (0, -signal.SIGINT):
        stderr = ""
        if process.stderr is not None:
            stderr = process.stderr.read().strip()
        raise RuntimeError(stderr or f"screencapture exited with status {process.returncode}.")


def _run_shell_command(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        shell=True,
        text=True,
        check=False,
        executable=os.environ.get("SHELL", "/bin/sh"),
    )


def execute_recorded_command(
    command: str,
    *,
    save_name: Optional[str] = None,
    pre_delay: float = 1.0,
    post_delay: float = 2.0,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    if pre_delay < 0 or post_delay < 0:
        raise ValueError("pre-delay and post-delay must be non-negative.")

    timestamp = now or datetime.now()
    video_path, metadata_path = _execution_capture_paths(command, save_name=save_name, now=timestamp)
    status = "FAILED"
    notes = "Recording did not start."
    exit_code = 1
    recorder: Optional[subprocess.Popen[str]] = None
    proof = {"proof_line": "", "proof_line_index": -1, "total_lines": 0}

    try:
        recorder = _start_screen_recording(video_path)
        notes = "Screen recording started with macOS screencapture."
        time.sleep(pre_delay)

        result = _run_shell_command(command)
        proof = _proof_metadata(result.stdout or "")
        exit_code = int(result.returncode)
        time.sleep(post_delay)

        _stop_screen_recording(recorder)
        recorder = None

        if exit_code == 0:
            status = "SUCCESS"
            notes = "Command completed and recording stopped cleanly."
        else:
            status = f"COMMAND_FAILED ({exit_code})"
            notes = "Command returned a non-zero exit code, but the recording artifact was still saved."
    except Exception as exc:
        status = "FAILED"
        notes = str(exc)
        if recorder is not None:
            try:
                _stop_screen_recording(recorder)
            except Exception:
                pass

    _write_execution_metadata(
        metadata_path,
        timestamp=timestamp,
        command=command,
        pre_delay=pre_delay,
        post_delay=post_delay,
        video_path=video_path,
        status=status,
        notes=notes,
        proof_line=str(proof["proof_line"]),
        proof_line_index=int(proof["proof_line_index"]),
        total_lines=int(proof["total_lines"]),
    )

    return {
        "status": status,
        "exit_code": exit_code if status != "FAILED" or exit_code != 1 else 1,
        "video_path": video_path,
        "metadata_path": metadata_path,
        "notes": notes,
        "proof_line": str(proof["proof_line"]),
        "proof_line_index": int(proof["proof_line_index"]),
        "total_lines": int(proof["total_lines"]),
    }


def _demo_summary(command: str) -> dict[str, str]:
    normalized = command.strip()
    if normalized in {"ari today", "ari networking today"}:
        return {
            "what_it_shows": "daily action surface with overdue and due follow-ups",
            "suggested_caption": "ARI showing me what matters today",
        }
    if normalized.startswith("ari docs content linkedin") or normalized.startswith("ari content linkedin"):
        return {
            "what_it_shows": "local content drafting turning active work into a post-ready update",
            "suggested_caption": "ARI turning live work into a reusable LinkedIn draft",
        }
    if normalized.startswith("ari docs script short-video") or normalized.startswith("ari script short-video"):
        return {
            "what_it_shows": "short-form script generation shaped from the existing ARI workflow",
            "suggested_caption": "ARI turning a build thread into a recordable short-form script",
        }
    if normalized.startswith("ari "):
        return {
            "what_it_shows": "a live ARI command running against the local system",
            "suggested_caption": "ARI in motion on a real local workflow",
        }
    return {
        "what_it_shows": "a local terminal workflow captured for a future demo asset",
        "suggested_caption": "Turning a working command into reusable proof of work",
    }


def _format_demo_output(command: str, result: subprocess.CompletedProcess[str], saved_path: Path) -> str:
    status = "SUCCESS" if result.returncode == 0 else f"FAILED ({result.returncode})"
    lines = [
        "DEMO CAPTURE",
        f"Command: {command}",
        f"Status: {status}",
        "",
        "STDOUT",
        result.stdout.rstrip() or "[no stdout]",
    ]
    if result.stderr:
        lines.extend(["", "STDERR", result.stderr.rstrip()])
    lines.extend(["", f"Saved: {saved_path}"])
    return "\n".join(lines)


def _save_demo_artifact(
    command: str,
    result: subprocess.CompletedProcess[str],
    save_name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Path:
    now_value = now or datetime.now()
    output_dir = Path.home() / "ARI" / "demos" / now_value.strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)

    if save_name:
        filename = f"{_sanitize_save_name(save_name)}.txt"
    else:
        filename = f"command-{now_value.strftime('%H%M%S')}.txt"

    summary = _demo_summary(command)
    output_path = output_dir / filename
    content = "\n".join(
        [
            f"Timestamp: {now_value.isoformat(timespec='seconds')}",
            f"Demo command: {command}",
            f"Exit code: {result.returncode}",
            f"What it shows: {summary['what_it_shows']}",
            f"Suggested caption: {summary['suggested_caption']}",
            "",
            "STDOUT",
            result.stdout.rstrip() or "[no stdout]",
            "",
            "STDERR",
            result.stderr.rstrip() or "[no stderr]",
        ]
    )
    output_path.write_text(content + "\n", encoding="utf-8")
    return output_path


def handle_demo_terminal(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    del db_path
    command = args.shell_command
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
        executable=os.environ.get("SHELL", "/bin/sh"),
    )
    saved_path = _save_demo_artifact(
        command=command,
        result=result,
        save_name=getattr(args, "save_name", None),
    )
    print(_format_demo_output(command, result, saved_path))
    return int(result.returncode)


def handle_demo_record(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    del db_path
    try:
        result = execute_recorded_command(
            args.shell_command,
            save_name=getattr(args, "save_name", None),
            pre_delay=getattr(args, "pre_delay", 1.0),
            post_delay=getattr(args, "post_delay", 2.0),
        )
    except Exception as exc:
        print("EXECUTION CAPTURE")
        print(f"Command: {args.shell_command}")
        print("Status: FAILED")
        print("Video: [unavailable]")
        print("Metadata: [unavailable]")
        print(f"Notes: {exc}")
        return 1
    print(
        _format_execution_summary(
            command=args.shell_command,
            status=result["status"],
            video_path=result["video_path"],
            metadata_path=result["metadata_path"],
        )
    )
    if result["status"] == "FAILED":
        print(f"Notes: {result['notes']}")
    return int(result["exit_code"])


def _session_demo_root() -> Path:
    return Path.home() / "ARI" / "demos"


def _session_output_dir(now: Optional[datetime] = None) -> Path:
    now_value = now or datetime.now()
    output_dir = Path.home() / "ARI" / "sessions" / now_value.strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _session_output_path(save_name: Optional[str] = None, now: Optional[datetime] = None) -> Path:
    now_value = now or datetime.now()
    output_dir = _session_output_dir(now_value)
    suffix = _sanitize_save_name(save_name) if save_name else "session"
    return output_dir / f"{now_value.strftime('%H%M%S')}-{suffix}.txt"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    ordered: OrderedDict[str, None] = OrderedDict()
    for value in values:
        cleaned = value.strip()
        if cleaned:
            ordered[cleaned] = None
    return list(ordered.keys())


def _is_meaningful_proof_line(line: str) -> bool:
    normalized = line.strip().lower()
    return normalized not in {"", "none", "[no stdout]", "[no stderr]"}


def _extract_paths(text: str) -> list[str]:
    matches = re.findall(r"(~\/[^\s]+|\/[^\s]+)", text)
    paths: list[str] = []
    for match in matches:
        cleaned = match.rstrip("),.;]'\"")
        expanded = str(Path(cleaned).expanduser())
        if expanded.startswith("/"):
            paths.append(expanded)
    return _dedupe_preserve_order(paths)


def _is_ari_artifact_path(path: str) -> bool:
    expanded = Path(path).expanduser()
    return "ARI" in expanded.parts


def _existing_paths(paths: list[str]) -> list[str]:
    existing: list[str] = []
    for path in paths:
        try:
            if Path(path).exists() and _is_ari_artifact_path(path):
                existing.append(path)
        except OSError:
            continue
    return _dedupe_preserve_order(existing)


def _artifact_kind(path: str) -> str:
    expanded = Path(path).expanduser()
    parts = {part.lower() for part in expanded.parts}
    suffix = expanded.suffix.lower()

    if "videos" in parts:
        return "video" if suffix != ".txt" else "video-metadata"
    if "clips" in parts:
        return "clip" if suffix != ".txt" else "clip-metadata"
    if "frames" in parts:
        return "frame" if suffix != ".txt" else "frame-metadata"
    if "sessions" in parts:
        return "session"
    if "demos" in parts:
        return "demo"
    return "other"


def _artifact_priority(path: str) -> tuple[int, int, str]:
    kind = _artifact_kind(path)
    priority_map = {
        "video": (5, 1),
        "clip": (5, 0),
        "frame": (4, 0),
        "session": (3, 0),
        "demo": (2, 0),
        "video-metadata": (1, 1),
        "clip-metadata": (1, 1),
        "frame-metadata": (1, 1),
        "other": (0, 0),
    }
    primary, asset_bias = priority_map.get(kind, (0, 0))
    return (primary, asset_bias, path)


def _sort_artifacts(paths: list[str]) -> list[str]:
    deduped = _dedupe_preserve_order(paths)
    return sorted(deduped, key=_artifact_priority, reverse=True)


def _structured_artifact_paths(
    artifact_path: Path,
    *,
    seen: Optional[set[str]] = None,
    max_depth: int = 2,
) -> list[str]:
    expanded_path = artifact_path.expanduser()
    normalized = str(expanded_path)
    seen_paths = seen if seen is not None else set()
    if normalized in seen_paths or max_depth < 0 or not expanded_path.exists() or expanded_path.suffix.lower() != ".txt":
        return []

    seen_paths.add(normalized)
    discovered_paths: list[str] = [normalized]
    for raw_line in expanded_path.read_text(encoding="utf-8").splitlines():
        if ": " not in raw_line:
            continue
        _, value = raw_line.split(": ", 1)
        nested_paths = _existing_paths(_extract_paths(value))
        discovered_paths.extend(nested_paths)
        for nested_path in nested_paths:
            discovered_paths.extend(
                _structured_artifact_paths(
                    Path(nested_path),
                    seen=seen_paths,
                    max_depth=max_depth - 1,
                )
            )

    return _dedupe_preserve_order(discovered_paths)


def _proof_candidate_score(line: str) -> tuple[int, int]:
    normalized = line.strip().lower()
    extracted_paths = _existing_paths(_extract_paths(line))
    best_priority = max((_artifact_priority(path)[0] for path in extracted_paths), default=0)
    path_score = 100 + best_priority if extracted_paths else 0
    marker_score = 0

    if normalized.startswith(("video:", "clip:", "frame:", "saved:", "saved demo artifact:", "saved session artifact:")):
        marker_score = 50
    elif normalized.startswith(("metadata:", "source:", "output ", "source video path:", "output video path:", "output clip path:", "output frame path:")):
        marker_score = 40
    elif normalized.startswith("status: success") or normalized == "success":
        marker_score = 20
    elif normalized.startswith("status:"):
        marker_score = 10

    return (path_score + marker_score, len(extracted_paths))


def _rank_proof_candidates(lines: list[str]) -> list[str]:
    deduped = _dedupe_preserve_order(lines)
    return sorted(
        deduped,
        key=lambda line: _proof_candidate_score(line),
        reverse=True,
    )


def _proof_subject(entry: dict[str, Any]) -> str:
    description = str(entry.get("description", "")).strip()
    if description:
        return description

    command = _strip_command_leakage(str(entry.get("command", "")).strip())
    if command:
        return command

    return "recent system behavior"


def _normalized_entry_description(command: str, description: str, stdout: str) -> str:
    cleaned_description = description.strip()
    generic_description = "a local terminal workflow captured for a future demo asset"
    if cleaned_description and cleaned_description.lower() != generic_description:
        return cleaned_description

    command_lower = command.strip().lower()
    stdout_upper = stdout.upper()
    if "VIDEO BUILD" in stdout_upper or " video build " in f" {command_lower} ":
        return "record a demo video of a real ARI command run"
    if "CLIP BUILD" in stdout_upper or " clip build " in f" {command_lower} ":
        return "generate a proof-focused clip from a recorded ARI run"
    if "FRAME BUILD" in stdout_upper or " frame build " in f" {command_lower} ":
        return "generate a framed artifact from a recorded ARI run"
    if "SESSION BUILD" in stdout_upper or " session build " in f" {command_lower} ":
        return "generate a session summary from recent ARI artifacts"
    return cleaned_description or generic_description


def _artifact_proof_sentence(path: str, entry: dict[str, Any]) -> str:
    subject = _proof_subject(entry)
    kind = _artifact_kind(path)

    if kind == "video":
        return _ensure_sentence(f"ARI recorded a demo video showing {subject} (saved at {path})")
    if kind == "clip":
        return _ensure_sentence(f"ARI generated a clipped demo showing {subject} (saved at {path})")
    if kind == "frame":
        return _ensure_sentence(f"ARI generated a framed artifact showing {subject} (saved at {path})")
    if kind == "session":
        return _ensure_sentence(f"ARI generated a session summary capturing {subject} (saved at {path})")
    if kind == "demo":
        return _ensure_sentence(f"ARI captured a demo transcript showing {subject} (saved at {path})")
    if kind in {"video-metadata", "clip-metadata", "frame-metadata"}:
        return _ensure_sentence(f"ARI saved supporting artifact metadata for {subject} (saved at {path})")
    return _ensure_sentence(f"ARI saved a supporting artifact for {subject} (saved at {path})")


def _fallback_proof_sentence(entry: dict[str, Any], raw_line: str) -> str:
    cleaned = raw_line.strip()
    lowered = cleaned.lower()
    if lowered.startswith(("ari can now", "ari generated", "ari recorded", "ari captured")):
        return _ensure_sentence(cleaned)

    description = str(entry.get("description", "")).strip()
    if description:
        capability = _to_capability_statement(description)
        return _ensure_sentence(f"{capability[:-1]} in a reviewable run")

    return _ensure_sentence("ARI generated reviewable evidence from a recent run")


def _build_entry_proof_points(
    entry: dict[str, Any],
    raw_proof_candidates: list[str],
    artifacts: list[str],
) -> list[str]:
    prioritized_artifacts = _sort_artifacts(artifacts)
    proof_points: list[str] = []

    for path in prioritized_artifacts:
        kind = _artifact_kind(path)
        if kind in {"video-metadata", "clip-metadata", "frame-metadata", "other"}:
            continue
        proof_points.append(_artifact_proof_sentence(path, entry))

    if proof_points:
        return _dedupe_preserve_order(proof_points)

    ranked_candidates = _rank_proof_candidates(raw_proof_candidates)
    if ranked_candidates:
        return [_fallback_proof_sentence(entry, ranked_candidates[0])]

    return []


def _parse_demo_file(demo_path: Path) -> dict[str, Any]:
    header_fields: dict[str, str] = {}
    sections: dict[str, list[str]] = {"stdout": [], "stderr": []}
    current_section: Optional[str] = None

    for raw_line in demo_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped.upper() in {"STDOUT", "STDERR"}:
            current_section = stripped.lower()
            continue

        if current_section is not None:
            sections[current_section].append(raw_line)
            continue

        if ": " in raw_line:
            key, value = raw_line.split(": ", 1)
            header_fields[key.strip().lower()] = value.strip()

    stdout = "\n".join(sections["stdout"]).strip()
    stderr = "\n".join(sections["stderr"]).strip()
    stdout_lines = [line.strip() for line in stdout.splitlines() if line.strip()]

    proof_candidates: list[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(marker in stripped for marker in ("Saved:", "Video:", "Clip:", "Frame:", "Metadata:", "Status:", "SUCCESS")):
            proof_candidates.append(stripped)
    if stdout_lines and _is_meaningful_proof_line(stdout_lines[-1]):
        proof_candidates.append(stdout_lines[-1])

    discovered_artifacts = _existing_paths(
        [str(demo_path)]
        + _extract_paths("\n".join(header_fields.values()))
        + _extract_paths(stdout)
        + _extract_paths(stderr)
    )

    nested_artifacts: list[str] = []
    for artifact in discovered_artifacts:
        nested_artifacts.extend(_structured_artifact_paths(Path(artifact)))
    artifacts = _sort_artifacts(discovered_artifacts + nested_artifacts)

    artifact_backed_candidates = [line for line in proof_candidates if _existing_paths(_extract_paths(line))]
    if not artifact_backed_candidates and str(demo_path) in artifacts:
        proof_candidates.append(f"Saved demo artifact: {demo_path}")

    entry_command = header_fields.get("demo command", header_fields.get("command", ""))
    entry_description = _normalized_entry_description(
        entry_command,
        header_fields.get("what it shows", ""),
        stdout,
    )
    entry = {
        "command": entry_command,
        "description": entry_description,
    }
    proof_points = _build_entry_proof_points(entry, proof_candidates, artifacts)

    return {
        "timestamp": header_fields.get("timestamp", ""),
        "command": str(entry["command"]),
        "stdout": stdout,
        "description": str(entry["description"]),
        "suggested_caption": header_fields.get("suggested caption", ""),
        "proof_points": proof_points,
        "artifacts": artifacts,
        "source_file": str(demo_path),
    }


def _entry_sort_key(entry: dict[str, Any]) -> tuple[str, str]:
    return str(entry.get("timestamp", "")).strip(), str(entry.get("source_file", ""))


def _collect_recent_demo_entries(limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []

    demo_root = _session_demo_root()
    if not demo_root.exists():
        return []

    entries = []
    for demo_path in demo_root.glob("*/*.txt"):
        if demo_path.is_file():
            entries.append(_parse_demo_file(demo_path))

    entries.sort(key=_entry_sort_key)
    recent_entries = entries[-limit:]
    recent_entries.sort(key=_entry_sort_key)
    return recent_entries


def _build_session_summary(
    entries: list[dict[str, Any]],
    proof_points: list[str],
    artifacts: list[str],
) -> str:
    if not entries:
        return "No demo activity was available to summarize."

    descriptions = _dedupe_preserve_order(
        [str(entry.get("description", "")).strip() for entry in entries if entry.get("description")]
    )
    commands = _dedupe_preserve_order(
        [str(entry.get("command", "")).strip() for entry in entries if entry.get("command")]
    )
    first_timestamp = entries[0].get("timestamp") or "unknown time"
    last_timestamp = entries[-1].get("timestamp") or "unknown time"

    parts = [
        (
            f"This session aggregates {len(entries)} recent demo "
            f"{'entry' if len(entries) == 1 else 'entries'} from {first_timestamp} to {last_timestamp}."
        )
    ]
    if descriptions:
        parts.append(f"It covers {'; '.join(descriptions[:3])}.")
    elif commands:
        parts.append(f"It is grounded in the commands {'; '.join(commands[:3])}.")

    if proof_points and artifacts:
        parts.append(
            f"Evidence includes {len(proof_points)} extracted proof point"
            f"{'' if len(proof_points) == 1 else 's'} and {len(artifacts)} referenced artifact"
            f"{'' if len(artifacts) == 1 else 's'}."
        )
    elif proof_points:
        parts.append(
            f"Evidence is mostly stdout-based with {len(proof_points)} extracted proof point"
            f"{'' if len(proof_points) == 1 else 's'} and no clearly referenced artifacts."
        )
    else:
        parts.append("Evidence is weak because the demo files did not expose clear proof markers beyond the saved captures.")

    return " ".join(parts)


def _classify_entry(entry: dict[str, Any]) -> str:
    command = str(entry.get("command", "")).strip().lower()
    description = str(entry.get("description", "")).strip().lower()
    text = f"{command} {description}"

    if command in {"ari today", "ari networking today"} or description.startswith("daily action surface"):
        return "operational"
    if any(
        token in text
        for token in (
            "linkedin",
            "short-form script",
            "short video",
            "script generation",
            "drafting",
            "post-ready",
            "recordable",
            "content",
        )
    ):
        return "output"
    if any(
        token in text
        for token in ("build", "built", "added", "created", "system", "layer", "workflow", "support")
    ):
        return "build"
    return "support"


def _entry_priority(entry: dict[str, Any]) -> int:
    entry_type = _classify_entry(entry)
    if entry_type == "build":
        return 3
    if entry_type == "output":
        return 2
    if entry_type == "support":
        return 1
    return 0


def _prioritized_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        entries,
        key=lambda entry: (_entry_priority(entry), _entry_sort_key(entry)),
        reverse=True,
    )
    return [entry for entry in ranked if _entry_priority(entry) > 0]


def _strip_command_leakage(text: str) -> str:
    cleaned = re.sub(r"`[^`]+`", "", text)
    cleaned = re.sub(r"\bari(?:\s+[A-Za-z0-9._/-]+)+\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bpython3\s+-m\s+networking_crm(?:\.[A-Za-z0-9_]+)*(?:\s+[A-Za-z0-9._/-]+)*\b", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" .,:;-")


def _tighten_sentence(text: str) -> str:
    cleaned = re.sub(r"\bthis allows me to\b", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bso that I can\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bI am able to\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bthe session now has concrete proof like\b", "Proof includes", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bthe session now has\b", "ARI now has", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bit matters because\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" .,:;-")


def _ensure_sentence(text: str) -> str:
    cleaned = _tighten_sentence(text)
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _to_capability_statement(text: str) -> str:
    cleaned = _strip_command_leakage(text.strip())
    if not cleaned:
        return "ARI can now deliver a clearer, reviewable system outcome."

    rewrites = (
        (r"(?i)\bi built a ([^.]+)", r"ARI can now \1"),
        (r"(?i)\bi built an ([^.]+)", r"ARI can now \1"),
        (r"(?i)\bi built ([^.]+)", r"ARI can now \1"),
        (r"(?i)\bi added support for ([^.]+)", r"ARI can now support \1"),
        (r"(?i)\bi added ([^.]+)", r"ARI can now \1"),
        (r"(?i)\bi created a system that ([^.]+)", r"ARI can now \1"),
        (r"(?i)\bi created a ([^.]+)", r"ARI can now \1"),
        (r"(?i)\bi created ([^.]+)", r"ARI can now \1"),
        (r"(?i)\bi worked on improving ([^.]+)", r"ARI can now improve \1"),
        (r"(?i)\bi worked on ([^.]+)", r"ARI can now improve \1"),
        (r"(?i)\bi tested ([^.]+)", r"ARI can now verify \1"),
    )
    for pattern, replacement in rewrites:
        candidate = re.sub(pattern, replacement, cleaned, count=1)
        if candidate != cleaned:
            cleaned = candidate
            break

    lower = cleaned.lower()
    if lower.startswith("local content drafting"):
        cleaned = "ARI can now turn active work into a reusable LinkedIn draft"
    elif lower.startswith("short-form script generation"):
        cleaned = "ARI can now turn a build thread into a recordable short video script"
    elif lower.startswith("daily action surface"):
        cleaned = "ARI can now surface the highest-priority follow-ups for today"
    elif not lower.startswith("ari can now"):
        cleaned = f"ARI can now {cleaned[:1].lower() + cleaned[1:]}" if cleaned else "ARI can now deliver a clearer system outcome"

    cleaned = re.sub(r"\ba live\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bthe existing\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bexisting\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\blocal\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = _tighten_sentence(cleaned)

    words = cleaned.split()
    if len(words) > 20:
        trimmed = words[:20]
        if trimmed[-1].endswith((".", "!", "?")):
            words = trimmed
        else:
            words = trimmed[:-1] + [trimmed[-1].rstrip(".,;:") + "."]
        cleaned = " ".join(words)

    cleaned = _ensure_sentence(cleaned)
    return cleaned[:1].upper() + cleaned[1:]


def _build_what_changed(entries: list[dict[str, Any]]) -> list[str]:
    prioritized = _prioritized_entries(entries)
    changes: list[str] = []
    for entry in prioritized:
        description = str(entry.get("description", "")).strip()
        if not description:
            continue
        capability = _to_capability_statement(description)
        entry_proof = _select_primary_proof([entry], list(entry.get("proof_points", [])))
        if entry_proof:
            changes.append(f"{capability} Evidence: {entry_proof}")
        else:
            changes.append(capability)
    changes = _dedupe_preserve_order(changes)
    if changes:
        return changes

    return _dedupe_preserve_order(
        [f"Command run: {entry['command']}" for entry in entries if str(entry.get("command", "")).strip()]
    )


def _strip_evidence_clause(text: str) -> str:
    cleaned = re.sub(r"\s+Evidence:\s+.+$", "", text.strip())
    return _ensure_sentence(cleaned) if cleaned else ""


def _build_linkedin_draft(
    entries: list[dict[str, Any]],
    what_changed: list[str],
    proof_points: list[str],
) -> str:
    prioritized = _prioritized_entries(entries)
    worked_on = (
        _strip_evidence_clause(what_changed[0])
        if what_changed
        else "ARI can now express recent progress as a concrete system capability."
    )
    changed_items = [_strip_evidence_clause(item) for item in (what_changed[1:] if len(what_changed) > 1 else what_changed)]
    changed = (
        " ".join(changed_items[:3])
        if changed_items
        else "The captured demos show activity, but the change signal is limited."
    )
    primary_proof = _select_primary_proof(entries, proof_points)
    why_matters = (
        f"Proof includes {primary_proof}."
        if primary_proof
        else "The documentation layer keeps execution tied to reviewable evidence."
    )
    if prioritized and not what_changed:
        description = str(prioritized[0].get("description", "")).strip()
        worked_on = _to_capability_statement(description) if description else worked_on
    return "\n".join(
        [
            f"What I worked on: {worked_on}",
            f"What changed: {_ensure_sentence(changed)}",
            f"Why it matters: {_proof_reference(why_matters)}",
        ]
    )


def _proof_reference(text: str) -> str:
    raw_text = re.sub(r"(?i)^proof includes\s+", "", text.strip()).strip()
    raw_lowered = raw_text.lower()
    if raw_lowered.startswith(("ari can now", "ari generated", "ari recorded", "ari captured")):
        return _ensure_sentence(raw_text)

    cleaned = _strip_command_leakage(raw_text)
    lowered = cleaned.lower()
    if "thin local drafting layer" in raw_lowered or "post-ready update" in raw_lowered:
        return "The output already produces a reusable LinkedIn draft from live work."
    if "script i would actually record" in raw_lowered or "recordable short-form script" in raw_lowered:
        return "The output already produces a recordable short video script."
    if any(marker in cleaned for marker in ("Saved:", "Clip:", "Status:", "/")):
        return _ensure_sentence(cleaned)
    if "recordable short" in lowered or ("script" in lowered and "record" in lowered):
        return "The output already produces a recordable short video script."
    if "linkedin" in lowered or "post-ready" in lowered or "drafting" in lowered:
        return "The output already produces a reusable LinkedIn draft from live work."
    return _ensure_sentence(cleaned)


def _proof_priority(proof_text: str) -> tuple[int, int]:
    paths = _existing_paths(_extract_paths(proof_text))
    best_priority = max((_artifact_priority(path)[0] for path in paths), default=0)
    return (best_priority, len(paths))


def _select_primary_proof(entries: list[dict[str, Any]], proof_points: list[str]) -> str:
    for entry in _prioritized_entries(entries):
        entry_proof_points = [str(point).strip() for point in entry.get("proof_points", []) if str(point).strip()]
        if entry_proof_points:
            return sorted(entry_proof_points, key=_proof_priority, reverse=True)[0]
    return sorted(proof_points, key=_proof_priority, reverse=True)[0] if proof_points else ""


def _build_short_video_script(
    entries: list[dict[str, Any]],
    summary: str,
    proof_points: list[str],
    what_changed: list[str],
) -> dict[str, str]:
    strongest_change = _strip_evidence_clause(what_changed[0]) if what_changed else ""
    hook_source = strongest_change or "ARI can now turn recent activity into a clear, reviewable capability."
    proof_line = _select_primary_proof(entries, proof_points) or (
        "Proof is limited to the saved demo captures, so the draft stays conservative."
    )

    return {
        "hook": _ensure_sentence(hook_source),
        "context": summary,
        "core_idea": strongest_change or "ARI can now convert execution into structured proof without inventing anything.",
        "proof": _proof_reference(proof_line),
        "close": "This is a draft layer over real local activity, ready for manual refinement if needed.",
    }


def _build_session_object(entries: list[dict[str, Any]], now: Optional[datetime] = None) -> dict[str, Any]:
    proof_points = sorted(
        _dedupe_preserve_order([point for entry in entries for point in entry.get("proof_points", [])]),
        key=_proof_priority,
        reverse=True,
    )
    artifacts = _sort_artifacts(
        [artifact for entry in entries for artifact in entry.get("artifacts", [])]
    )
    what_changed = _build_what_changed(entries)
    summary = _build_session_summary(entries, proof_points, artifacts)

    return {
        "session_timestamp": (now or datetime.now()).isoformat(timespec="seconds"),
        "entries": entries,
        "summary": summary,
        "what_changed": what_changed,
        "proof_points": proof_points,
        "artifacts": artifacts,
        "linkedin_draft": _build_linkedin_draft(entries, what_changed, proof_points),
        "short_video_script": _build_short_video_script(entries, summary, proof_points, what_changed),
    }


def _render_list(items: list[str], empty_message: str) -> list[str]:
    if not items:
        return [f"- {empty_message}"]
    return [f"- {item}" for item in items]


def _render_session_file(session: dict[str, Any]) -> str:
    lines = [
        "SESSION",
        f"Session timestamp: {session['session_timestamp']}",
        f"Entries processed: {len(session['entries'])}",
        "",
        "ENTRIES",
    ]

    for index, entry in enumerate(session["entries"], start=1):
        lines.extend(
            [
                "",
                f"Entry {index}",
                f"Timestamp: {entry.get('timestamp', '')}",
                f"Command: {entry.get('command', '')}",
                f"Description: {entry.get('description', '')}",
                f"Suggested caption: {entry.get('suggested_caption', '')}",
                "Proof points:",
            ]
        )
        lines.extend(_render_list(entry.get("proof_points", []), "[none found]"))
        lines.append("Artifacts:")
        lines.extend(_render_list(entry.get("artifacts", []), "[none found]"))
        lines.extend(["STDOUT", entry.get("stdout", "") or "[blank]"])

    lines.extend(["", "SESSION SUMMARY", session["summary"], "", "WHAT CHANGED"])
    lines.extend(
        _render_list(
            session["what_changed"],
            "Evidence was too thin to identify concrete changes beyond the captured commands.",
        )
    )
    lines.extend(["", "PROOF POINTS"])
    lines.extend(
        _render_list(session["proof_points"], "No explicit proof points were extracted from the recent demo files.")
    )
    lines.extend(["", "ARTIFACTS"])
    lines.extend(
        _render_list(session["artifacts"], "No artifact paths were clearly referenced in the recent demo files.")
    )
    lines.extend(
        [
            "",
            "LINKEDIN DRAFT",
            session["linkedin_draft"],
            "",
            "SHORT VIDEO SCRIPT",
            f"HOOK: {session['short_video_script']['hook']}",
            f"CONTEXT: {session['short_video_script']['context']}",
            f"CORE IDEA: {session['short_video_script']['core_idea']}",
            f"PROOF: {session['short_video_script']['proof']}",
            f"CLOSE: {session['short_video_script']['close']}",
        ]
    )
    return "\n".join(lines) + "\n"


def handle_session_build(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    del db_path
    entries = _collect_recent_demo_entries(getattr(args, "limit", 5))
    if not entries:
        print("SESSION BUILD")
        print("")
        print("Status: ERROR")
        print("")
        print("Reason:")
        print("  no demo files found in ~/ARI/demos")
        return 1

    now_value = datetime.now()
    session = _build_session_object(entries, now=now_value)
    output_path = _session_output_path(getattr(args, "save_name", None), now=now_value)
    output_path.write_text(_render_session_file(session), encoding="utf-8")

    print("SESSION BUILD")
    print("")
    print("Status: SUCCESS")
    print("")
    print("Saved:")
    print(f"  {output_path}")
    print("")
    print("Entries processed:")
    print(f"  {len(session['entries'])}")
    print("")
    print("Proof points found:")
    print(f"  {len(session['proof_points'])}")
    print("")
    print("Artifacts found:")
    print(f"  {len(session['artifacts'])}")
    print("")
    print("Next step:")
    print("  review the structured session and refine into final content if needed")
    return 0
