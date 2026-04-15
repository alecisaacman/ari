import argparse
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .demo import _sanitize_save_name
from ...core.paths import DB_PATH


TERMINAL_APPS = {"Terminal", "iTerm2", "iTerm"}
BROWSER_APPS = {"Google Chrome", "Arc", "Safari"}


@dataclass(frozen=True)
class WindowBounds:
    app_name: str
    title: str
    x: int
    y: int
    width: int
    height: int
    is_frontmost: bool = False


@dataclass(frozen=True)
class ScreenBounds:
    width: int
    height: int


@dataclass(frozen=True)
class CropBounds:
    x: int
    y: int
    width: int
    height: int


def _frame_artifact_slug(source_video: Path, save_name: Optional[str] = None) -> str:
    if save_name:
        return _sanitize_save_name(save_name)

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", source_video.stem.strip().lower()).strip("-._")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned[:64] or "frame"


def _frame_output_paths(
    source_video: Path,
    *,
    save_name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> tuple[Path, Path]:
    now_value = now or datetime.now()
    output_dir = Path.home() / "ARI" / "frames" / now_value.strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{now_value.strftime('%H%M%S')}-{_frame_artifact_slug(source_video, save_name)}"
    return output_dir / f"{base_name}.mov", output_dir / f"{base_name}.txt"


def _write_frame_metadata(
    metadata_path: Path,
    *,
    timestamp: datetime,
    source_video_path: Path,
    output_frame_path: Path,
    mode: str,
    width: int,
    height: int,
    anchor: str,
    detected_app: str,
    detected_title: str,
    detected_bounds: str,
    padding: int,
    fallback_used: str,
    status: str,
    notes: str,
) -> Path:
    lines = [
        f"timestamp: {timestamp.isoformat(timespec='seconds')}",
        f"source video path: {source_video_path}",
        f"output frame path: {output_frame_path}",
        f"mode: {mode}",
        f"width: {width}",
        f"height: {height}",
        f"anchor: {anchor}",
        f"detected_app: {detected_app}",
        f"detected_title: {detected_title}",
        f"detected_bounds: {detected_bounds}",
        f"padding: {padding}",
        f"fallback_used: {fallback_used}",
        f"status: {status}",
        f"notes: {notes}",
    ]
    metadata_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return metadata_path


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def _validate_frame_request(source_video: Path, mode: str, width: int, height: int, padding: int) -> None:
    if not source_video.exists():
        raise FileNotFoundError(f"Source video not found: {source_video}")
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive integers. Try --width 800 --height 600.")
    if mode == "vertical" and (width <= 0 or height <= 0):
        raise ValueError("vertical mode requires valid source dimensions. Try --width 800 --height 600.")
    if padding < 0:
        raise ValueError("padding must be zero or a positive integer. Try --padding 40.")


def _run_osascript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "AppleScript window detection failed."
        lowered = message.lower()
        if "not authorized" in lowered or "not permitted" in lowered or "(-1743)" in lowered:
            raise RuntimeError("AppleScript access denied")
        raise RuntimeError(message)
    return result.stdout.strip()


def _parse_window_listing(raw_output: str, frontmost_app: Optional[str] = None) -> list[WindowBounds]:
    windows: list[WindowBounds] = []
    for raw_line in raw_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 6:
            continue
        app_name, title, x_value, y_value, width_value, height_value = parts
        try:
            x_pos = int(float(x_value))
            y_pos = int(float(y_value))
            width = int(float(width_value))
            height = int(float(height_value))
        except ValueError:
            continue
        if width <= 0 or height <= 0:
            continue
        windows.append(
            WindowBounds(
                app_name=app_name.strip(),
                title=title.strip(),
                x=x_pos,
                y=y_pos,
                width=width,
                height=height,
                is_frontmost=app_name.strip() == (frontmost_app or "").strip(),
            )
        )
    return windows


def _frontmost_app_name() -> Optional[str]:
    script = """
tell application "System Events"
    set frontmostProcess to first application process whose frontmost is true
    return name of frontmostProcess
end tell
""".strip()
    output = _run_osascript(script)
    return output or None


def _screen_bounds() -> ScreenBounds:
    script = 'tell application "Finder" to get bounds of window of desktop'
    output = _run_osascript(script)
    parts = [part.strip() for part in output.split(",")]
    if len(parts) != 4:
        raise RuntimeError("Unable to determine screen bounds.")
    try:
        left, top, right, bottom = [int(float(part)) for part in parts]
    except ValueError as exc:
        raise RuntimeError("Unable to parse screen bounds.") from exc
    width = max(0, right - left)
    height = max(0, bottom - top)
    if width <= 0 or height <= 0:
        raise RuntimeError("Unable to determine screen bounds.")
    return ScreenBounds(width=width, height=height)


def _visible_windows() -> list[WindowBounds]:
    frontmost_app = _frontmost_app_name()
    script = """
set outputLines to {}
set AppleScript's text item delimiters to linefeed
tell application "System Events"
    repeat with proc in (application processes where background only is false)
        try
            if visible of proc then
                set appName to name of proc
                repeat with win in windows of proc
                    try
                        set winTitle to name of win
                        set {xPos, yPos} to position of win
                        set {winWidth, winHeight} to size of win
                        copy (appName & tab & winTitle & tab & (xPos as string) & tab & (yPos as string) & tab & (winWidth as string) & tab & (winHeight as string)) to end of outputLines
                    end try
                end repeat
            end if
        end try
    end repeat
end tell
if (count of outputLines) is 0 then
    return ""
end if
return outputLines as string
""".strip()
    raw_output = _run_osascript(script)
    return _parse_window_listing(raw_output, frontmost_app=frontmost_app)


def _probe_video_dimensions(source_video: Path) -> tuple[int, int]:
    if not _ffprobe_available():
        raise RuntimeError("ffprobe is not installed. Install ffmpeg to probe frame dimensions.")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(source_video),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        notes = result.stderr.strip() or result.stdout.strip() or "Unable to probe source video dimensions."
        raise RuntimeError(notes)
    match = re.search(r"(\d+)x(\d+)", result.stdout.strip())
    if not match:
        raise RuntimeError("Unable to parse source video dimensions.")
    return int(match.group(1)), int(match.group(2))


def _expand_bounds(bounds: WindowBounds, padding: int) -> CropBounds:
    return CropBounds(
        x=bounds.x - padding,
        y=bounds.y - padding,
        width=bounds.width + (padding * 2),
        height=bounds.height + (padding * 2),
    )


def _scale_window_bounds(bounds: CropBounds, screen_bounds: ScreenBounds, video_width: int, video_height: int) -> CropBounds:
    scale_x = video_width / screen_bounds.width
    scale_y = video_height / screen_bounds.height
    return CropBounds(
        x=int(round(bounds.x * scale_x)),
        y=int(round(bounds.y * scale_y)),
        width=max(1, int(round(bounds.width * scale_x))),
        height=max(1, int(round(bounds.height * scale_y))),
    )


def _clamp_crop_origin(target_start: int, target_length: int, crop_length: int, max_length: int) -> int:
    if crop_length >= max_length:
        return 0

    lower_bound = 0
    upper_bound = max_length - crop_length
    target_end = target_start + target_length

    if target_length < crop_length:
        min_origin = math.ceil(target_end - crop_length)
        max_origin = math.floor(target_start)
        ideal_origin = round(target_start + (target_length / 2) - (crop_length / 2))
        if min_origin <= max_origin:
            ideal_origin = min(max(ideal_origin, min_origin), max_origin)
        return min(max(ideal_origin, lower_bound), upper_bound)

    ideal_origin = round(target_start + (target_length / 2) - (crop_length / 2))
    return min(max(ideal_origin, lower_bound), upper_bound)


def _vertical_crop_size(video_width: int, video_height: int) -> tuple[int, int]:
    crop_width = int(round(video_height * 9 / 16))
    crop_height = video_height
    if crop_width > video_width:
        crop_width = video_width
        crop_height = int(round(video_width * 16 / 9))
        crop_height = min(crop_height, video_height)
    return max(1, crop_width), max(1, crop_height)


def _calculate_crop_bounds(
    *,
    mode: str,
    video_width: int,
    video_height: int,
    crop_width: int,
    crop_height: int,
    target_bounds: Optional[CropBounds],
) -> CropBounds:
    if mode == "vertical":
        crop_width, crop_height = _vertical_crop_size(video_width, video_height)
    else:
        crop_width = min(crop_width, video_width)
        crop_height = min(crop_height, video_height)

    if target_bounds is None:
        crop_x = max(0, round((video_width - crop_width) / 2))
        crop_y = max(0, round((video_height - crop_height) / 2))
        return CropBounds(x=crop_x, y=crop_y, width=crop_width, height=crop_height)

    crop_x = _clamp_crop_origin(target_bounds.x, target_bounds.width, crop_width, video_width)
    crop_y = _clamp_crop_origin(target_bounds.y, target_bounds.height, crop_height, video_height)
    return CropBounds(x=crop_x, y=crop_y, width=crop_width, height=crop_height)


def _frame_filter(crop_bounds: CropBounds, mode: str) -> str:
    base = f"crop={crop_bounds.width}:{crop_bounds.height}:{crop_bounds.x}:{crop_bounds.y}"
    if mode == "vertical":
        return f"{base},scale=1080:1920"
    return base


def _first_title_match(windows: list[WindowBounds], window_title: Optional[str]) -> Optional[WindowBounds]:
    if not window_title:
        return None
    needle = window_title.strip().lower()
    if not needle:
        return None
    for window in windows:
        if needle in window.title.lower():
            return window
    return None


def _filter_windows_by_apps(windows: list[WindowBounds], app_names: set[str]) -> list[WindowBounds]:
    return [window for window in windows if window.app_name in app_names]


def _frontmost_window(windows: list[WindowBounds]) -> Optional[WindowBounds]:
    for window in windows:
        if window.is_frontmost:
            return window
    return windows[0] if windows else None


def _select_anchor_window(
    *,
    anchor: str,
    window_title: Optional[str],
    windows: list[WindowBounds],
) -> tuple[Optional[WindowBounds], bool, str]:
    if not windows:
        return None, True, "no suitable window detected"

    title_match = _first_title_match(windows, window_title)
    if title_match is not None:
        if anchor == "browser" and title_match.app_name not in BROWSER_APPS:
            pass
        elif anchor == "terminal" and title_match.app_name not in TERMINAL_APPS:
            pass
        else:
            return title_match, False, ""

    frontmost = _frontmost_window(windows)
    terminal_windows = _filter_windows_by_apps(windows, TERMINAL_APPS)
    browser_windows = _filter_windows_by_apps(windows, BROWSER_APPS)

    if anchor == "frontmost":
        if frontmost is None:
            return None, True, "no suitable window detected"
        return frontmost, False, ""

    if anchor == "terminal":
        if frontmost is not None and frontmost.app_name in TERMINAL_APPS:
            return frontmost, False, ""
        if terminal_windows:
            return terminal_windows[0], False, ""
        return None, True, "no suitable window detected"

    if anchor == "browser":
        if frontmost is not None and frontmost.app_name in BROWSER_APPS:
            return frontmost, False, ""
        if browser_windows:
            return browser_windows[0], False, ""
        return None, True, "no suitable window detected"

    if anchor == "auto":
        if frontmost is not None and frontmost.app_name in TERMINAL_APPS:
            return frontmost, False, ""
        if frontmost is not None and frontmost.app_name in BROWSER_APPS:
            return frontmost, False, ""
        if frontmost is not None:
            return frontmost, False, ""
        return None, True, "no suitable window detected"

    raise ValueError(f"Unsupported anchor mode: {anchor}")


def _resolve_anchor_crop(
    *,
    source_video: Path,
    mode: str,
    anchor: str,
    window_title: Optional[str],
    padding: int,
    width: int,
    height: int,
) -> tuple[CropBounds, Optional[WindowBounds], bool]:
    video_width, video_height = _probe_video_dimensions(source_video)
    windows = _visible_windows()
    selected_window, should_fallback, reason = _select_anchor_window(
        anchor=anchor,
        window_title=window_title,
        windows=windows,
    )

    if selected_window is None:
        if anchor != "auto":
            raise RuntimeError(reason or "no suitable window detected")
        crop_bounds = _calculate_crop_bounds(
            mode=mode,
            video_width=video_width,
            video_height=video_height,
            crop_width=width,
            crop_height=height,
            target_bounds=None,
        )
        return crop_bounds, None, True

    screen_bounds = _screen_bounds()
    target_bounds = _scale_window_bounds(
        _expand_bounds(selected_window, padding),
        screen_bounds,
        video_width,
        video_height,
    )
    crop_bounds = _calculate_crop_bounds(
        mode=mode,
        video_width=video_width,
        video_height=video_height,
        crop_width=width,
        crop_height=height,
        target_bounds=target_bounds,
    )
    return crop_bounds, selected_window, False


def _run_frame_command(source_video: Path, output_frame_path: Path, crop_bounds: CropBounds, mode: str) -> None:
    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg is not installed. Install ffmpeg to build frames.")

    filter_value = _frame_filter(crop_bounds, mode)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source_video),
            "-vf",
            filter_value,
            str(output_frame_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        notes = result.stderr.strip() or result.stdout.strip() or "ffmpeg frame build failed."
        raise RuntimeError(notes)


def _failure_guidance(
    notes: str,
    source_video: Path,
    metadata_path: Optional[Path],
) -> str:
    reason = notes.strip() or "Frame build failed."
    next_step = "review the error details and rerun the frame build command"

    if "ffmpeg is not installed" in reason:
        reason = "ffmpeg is not installed"
        next_step = "brew install ffmpeg"
    elif "ffprobe is not installed" in reason:
        reason = "ffprobe is not installed"
        next_step = "brew install ffmpeg"
    elif "Source video not found" in reason:
        next_step = "verify the source video exists at the provided path"
    elif "width and height must be positive integers" in reason:
        next_step = "rerun with valid dimensions such as --width 800 --height 600"
    elif "padding must be zero or a positive integer" in reason:
        next_step = "rerun with a valid integer such as --padding 40"
    elif "AppleScript access denied" in reason:
        next_step = "allow Terminal automation and rerun the frame build command"
    elif "no suitable window detected" in reason:
        next_step = "bring the target window on screen or rerun with --anchor auto"

    lines = [
        "FRAME BUILD",
        "",
        f"Source: {source_video}",
        "Status: FAILED",
        f"Reason: {reason}",
        "",
        "Next step:",
        f"  {next_step}",
        "",
        "Metadata saved:" if metadata_path is not None else "Metadata unavailable:",
        f"  {metadata_path}" if metadata_path is not None else "  [unavailable]",
    ]
    return "\n".join(lines)


def _format_frame_result(result: dict[str, object]) -> str:
    source_video = result["source_video"]
    status = result["status"]
    frame_path = result["frame_path"]
    metadata_path = result["metadata_path"]
    notes = str(result["notes"])

    if status == "SUCCESS":
        detected_app = str(result.get("detected_app") or "[none]")
        detected_title = str(result.get("detected_title") or "[none]")
        detected_bounds = str(result.get("detected_bounds") or "[none]")
        fallback_used = bool(result.get("fallback_used"))
        next_step = (
            "review whether the framed output keeps the terminal readable and centered"
            if str(result.get("mode")) == "terminal"
            else "review whether the framed output keeps the important window visible and centered"
        )
        lines = [
            "FRAME BUILD",
            "",
            f"Source: {source_video}",
            f"Mode: {result['mode']}",
            f"Anchor: {result['anchor']}",
            "Detected window:",
            f"  App: {detected_app}",
            f"  Title: {detected_title}",
            f"  Bounds: {detected_bounds}",
        ]
        if fallback_used:
            lines.extend(
                [
                    "Fallback:",
                    "  center crop used because no suitable window was detected",
                ]
            )
        lines.extend(
            [
                f"Frame: {frame_path}",
                f"Metadata: {metadata_path}",
                "",
                "Next step:",
                f"  {next_step}",
            ]
        )
        return "\n".join(lines)

    return _failure_guidance(notes, source_video, metadata_path)


def build_frame(
    source_video: str,
    *,
    save_name: Optional[str] = None,
    mode: str = "terminal",
    anchor: str = "auto",
    window_title: Optional[str] = None,
    padding: int = 40,
    width: int = 800,
    height: int = 600,
    now: Optional[datetime] = None,
) -> dict[str, object]:
    timestamp = now or datetime.now()
    source_path = Path(source_video).expanduser()
    output_frame_path, metadata_path = _frame_output_paths(source_path, save_name=save_name, now=timestamp)

    status = "FAILED"
    notes = "Frame build did not start."
    exit_code = 1
    crop_bounds = CropBounds(x=0, y=0, width=width, height=height)
    detected_window: Optional[WindowBounds] = None
    fallback_used = False

    try:
        _validate_frame_request(source_path, mode, width, height, padding)
        crop_bounds, detected_window, fallback_used = _resolve_anchor_crop(
            source_video=source_path,
            mode=mode,
            anchor=anchor,
            window_title=window_title,
            padding=padding,
            width=width,
            height=height,
        )
        _run_frame_command(source_path, output_frame_path, crop_bounds, mode)
        status = "SUCCESS"
        notes = "Frame built successfully with ffmpeg."
        exit_code = 0
    except Exception as exc:
        notes = str(exc)

    _write_frame_metadata(
        metadata_path,
        timestamp=timestamp,
        source_video_path=source_path,
        output_frame_path=output_frame_path,
        mode=mode,
        width=crop_bounds.width,
        height=crop_bounds.height,
        anchor=anchor,
        detected_app=detected_window.app_name if detected_window is not None else "",
        detected_title=detected_window.title if detected_window is not None else "",
        detected_bounds=(
            f"{detected_window.x},{detected_window.y},{detected_window.width},{detected_window.height}"
            if detected_window is not None
            else ""
        ),
        padding=padding,
        fallback_used="yes" if fallback_used else "no",
        status=status,
        notes=notes,
    )

    return {
        "status": status,
        "exit_code": exit_code,
        "source_video": source_path,
        "frame_path": output_frame_path,
        "metadata_path": metadata_path,
        "mode": mode,
        "anchor": anchor,
        "window_title": window_title,
        "padding": padding,
        "width": crop_bounds.width,
        "height": crop_bounds.height,
        "detected_app": detected_window.app_name if detected_window is not None else "",
        "detected_title": detected_window.title if detected_window is not None else "",
        "detected_bounds": (
            f"{detected_window.x},{detected_window.y},{detected_window.width},{detected_window.height}"
            if detected_window is not None
            else ""
        ),
        "fallback_used": fallback_used,
        "notes": notes,
    }


def handle_frame_build(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    del db_path
    try:
        result = build_frame(
            args.video,
            save_name=getattr(args, "save_name", None),
            mode=getattr(args, "mode", "terminal"),
            anchor=getattr(args, "anchor", "auto"),
            window_title=getattr(args, "window_title", None),
            padding=getattr(args, "padding", 40),
            width=getattr(args, "width", 800),
            height=getattr(args, "height", 600),
        )
    except Exception as exc:
        source_path = Path(args.video).expanduser()
        print(_failure_guidance(str(exc), source_path, None))
        return 1

    print(_format_frame_result(result))
    return int(result["exit_code"])
