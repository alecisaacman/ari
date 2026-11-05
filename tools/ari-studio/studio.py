"""ARI's studio: turns a building day's approved script into a finished vertical video.

    ~/ARI/media/venv/bin/python tools/ari-studio/studio.py produce --day 23 [--script 1]

1. Narration: each line of the script (the hook, then each beat, then the sign-off) is
   spoken in Alec's cloned voice by Chatterbox, an open-source voice-cloning model, from
   his one-minute sample (~/ARI/media/voice/alec-sample.wav). With no sample yet it uses
   Chatterbox's default voice, so the pipeline can be checked end to end. Chatterbox runs
   on Replicate's GPUs, paid per second (this Mac's 8 GB can't hold it), under a monthly
   cap (ARI_STUDIO_MONTHLY_USD, $5); ARI_STUDIO_VOICE=local runs it here instead, for
   when ARI moves to a bigger Mac.
2. Footage: real material from that day. The code that changed comes from the public
   repository's commits for the day; the cards and the sign-off show the hook and ARI's
   hummingbird. Nothing personal (texts, calendar, to-dos) goes in: the video is public.
3. Captions: two to four words at a time, bold, timed across each spoken line.
4. The cut: ffmpeg zooms slowly through each shot, lays the captions over it, and joins
   the shots with the narration into a 1080 x 1920 MP4 under ~/ARI/media/out.

Cards and captions are drawn by headless Chrome from HTML, because this ffmpeg build
has no text drawing. The heavy model lives in its own environment (~/ARI/media/venv),
never in ARI's runtime.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

HOME = Path.home()
ARI_HOME = Path(os.environ.get("ARI_HOME", HOME / "ARI"))
MEDIA = ARI_HOME / "media"
VOICE_SAMPLE = MEDIA / "voice" / "alec-sample.wav"
OUT = MEDIA / "out"
ARI_CLI = ARI_HOME / "runtime" / "current" / ".venv" / "bin" / "ari"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PET_ART = Path(__file__).resolve().parents[1] / "ari-pet" / "art" / "ari"
WIDTH, HEIGHT, FPS = 1080, 1920, 30
# A short breath between lines, so the narration doesn't run together.
PAUSE_SECONDS = 0.25
WORDS_PER_CAPTION = 3
CODE_LINES = 22
REPLICATE = "https://api.replicate.com/v1"
REPLICATE_MODEL = "resemble-ai/chatterbox"
# Replicate doesn't publish this model's price, so every second of GPU time is counted at
# its dearest GPU's rate (an A100, $0.0014 a second): the cap can only stop early.
REPLICATE_USD_PER_SECOND = 0.0014
DEFAULT_MONTHLY_USD = 5.0
SPEND = MEDIA / "studio-spend.json"


@dataclass
class Line:
    text: str
    shot: Path
    audio: Path | None = None
    seconds: float = 0.0


def produce(day_number: int, script_index: int, keep: bool = False) -> Path:
    item = _content_item(day_number)
    scripts = item.get("scripts") or []
    if not scripts:
        raise SystemExit(f"Day {day_number} has no script.")
    script = scripts[min(script_index, len(scripts)) - 1]
    work = Path(tempfile.mkdtemp(prefix=f"ari-studio-day{day_number}-"))
    try:
        lines = _plan(item, script, work)
        _narrate(lines, work)
        captions = _captions(lines, work)
        out = _cut(lines, captions, work, day_number)
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)
    return out


# --- Plan: what is said, over which shot ---------------------------------------------


def _plan(item: dict, script: dict, work: Path) -> list[Line]:
    day = item["dayNumber"]
    hook = script.get("hook") or item.get("hook") or ""
    beats = [beat for beat in script.get("beats") or [] if beat.strip()]
    code = _code_shots(item.get("date"), len(beats), work)
    lines = [Line(_spoken(hook), _card(work, "hook", day=day, big=hook, label=f"DAY {day} OF BUILDING ARI"))]
    for index, beat in enumerate(beats):
        shot = code[index % len(code)] if code else _card(work, f"beat{index}", day=day, big=beat, label=f"DAY {day}")
        lines.append(Line(_spoken(beat), shot))
    sign_off = f"Day {day} of building ARI. Follow along for day {day + 1}."
    lines.append(Line(sign_off, _card(work, "end", day=day, big=f"Day {day} of building ARI", label="FOLLOW ALONG", bird=True)))
    return lines


def _spoken(text: str) -> str:
    """Beats are written as notes ("Fix: 8000 tokens"); say them as sentences."""
    text = re.sub(r"^(\w[\w ]{0,20}):\s+", lambda m: f"The {m.group(1).lower()}: " if m.group(1).lower() in ("fix", "lesson", "cause") else m.group(0), text.strip())
    return text if text.endswith((".", "?", "!")) else f"{text}."


# --- Narration -----------------------------------------------------------------------


def _narrate(lines: list[Line], work: Path) -> None:
    if _voice_backend() == "replicate":
        _narrate_replicate(lines, work)
    else:
        _narrate_local(lines, work)
    for line in lines:
        line.seconds = _duration(line.audio) + PAUSE_SECONDS


def _voice_backend() -> str:
    chosen = os.environ.get("ARI_STUDIO_VOICE") or _env_value("ARI_STUDIO_VOICE")
    if chosen:
        return chosen
    return "replicate" if _replicate_token() else "local"


def _narrate_local(lines: list[Line], work: Path) -> None:
    import torchaudio as ta
    from chatterbox.tts import ChatterboxTTS

    device = "mps" if _mps() else "cpu"
    model = ChatterboxTTS.from_pretrained(device=device)
    if not _watermark_wanted():
        model.watermarker = _NoWatermark()
    sample = str(VOICE_SAMPLE) if VOICE_SAMPLE.exists() else None
    for index, line in enumerate(lines):
        audio = model.generate(line.text, audio_prompt_path=sample) if sample else model.generate(line.text)
        line.audio = work / f"line{index:02d}.wav"
        ta.save(str(line.audio), audio, model.sr)


# --- Narration on Replicate, under a monthly cap -------------------------------------


class OverBudget(RuntimeError):
    """This month's studio budget is spent; the video waits for next month or a higher cap."""


def _narrate_replicate(lines: list[Line], work: Path) -> None:
    _check_budget()
    sample_url = _upload_sample(work) if VOICE_SAMPLE.exists() else None
    for index, line in enumerate(lines):
        _check_budget()
        payload = {"prompt": line.text, "exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.8}
        if sample_url:
            payload["audio_prompt"] = sample_url
        output, seconds = _predict(payload)
        _record_spend(seconds)
        line.audio = work / f"line{index:02d}.wav"
        with urllib.request.urlopen(output, timeout=60) as response:
            line.audio.write_bytes(response.read())


def _predict(payload: dict) -> tuple[str, float]:
    """Run one prediction; returns the audio's URL and the GPU seconds it was billed for."""
    prediction = _replicate("POST", f"/models/{REPLICATE_MODEL}/predictions", {"input": payload}, wait=True)
    deadline = time.monotonic() + 300
    while prediction.get("status") not in ("succeeded", "failed", "canceled"):
        if time.monotonic() > deadline:
            raise RuntimeError("Replicate took more than five minutes on one line.")
        time.sleep(1.5)
        prediction = _replicate("GET", f"/predictions/{prediction['id']}")
    seconds = float((prediction.get("metrics") or {}).get("predict_time") or 0)
    if prediction["status"] != "succeeded":
        _record_spend(seconds)
        raise RuntimeError(f"Replicate couldn't narrate a line: {prediction.get('error') or prediction['status']}")
    output = prediction["output"]
    return (output[0] if isinstance(output, list) else output), seconds


def _upload_sample(work: Path) -> str:
    """Alec's sample, made small (mono MP3) and uploaded once per video."""
    small = work / "sample.mp3"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(VOICE_SAMPLE), "-ac", "1",
                    "-ar", "24000", "-b:a", "96k", str(small)], check=True)
    boundary = "ari-studio-boundary"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="content"; filename="sample.mp3"\r\n'
        "Content-Type: audio/mpeg\r\n\r\n"
    ).encode() + small.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        f"{REPLICATE}/files", data=body, method="POST",
        headers={"Authorization": f"Bearer {_replicate_token()}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())["urls"]["get"]


def _replicate(method: str, path: str, body: dict | None = None, wait: bool = False) -> dict:
    headers = {"Authorization": f"Bearer {_replicate_token()}", "Content-Type": "application/json"}
    if wait:
        headers["Prefer"] = "wait=60"
    request = urllib.request.Request(
        f"{REPLICATE}{path}", data=json.dumps(body).encode() if body is not None else None, method=method, headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Replicate said {error.code}: {error.read().decode()[:200]}") from error


def _replicate_token() -> str | None:
    return os.environ.get("REPLICATE_API_TOKEN") or _env_value("REPLICATE_API_TOKEN")


def monthly_cap() -> float:
    value = os.environ.get("ARI_STUDIO_MONTHLY_USD") or _env_value("ARI_STUDIO_MONTHLY_USD")
    try:
        return float(value) if value else DEFAULT_MONTHLY_USD
    except ValueError:
        return DEFAULT_MONTHLY_USD


def spent_this_month(now: datetime | None = None) -> float:
    month = (now or datetime.now(tz=UTC)).strftime("%Y-%m")
    try:
        ledger = json.loads(SPEND.read_text())
    except (OSError, ValueError):
        return 0.0
    return float(ledger.get(month, {}).get("usd", 0.0))


def _record_spend(seconds: float, now: datetime | None = None) -> None:
    month = (now or datetime.now(tz=UTC)).strftime("%Y-%m")
    try:
        ledger = json.loads(SPEND.read_text())
    except (OSError, ValueError):
        ledger = {}
    entry = ledger.setdefault(month, {"seconds": 0.0, "usd": 0.0})
    entry["seconds"] = round(entry["seconds"] + seconds, 3)
    entry["usd"] = round(entry["usd"] + seconds * REPLICATE_USD_PER_SECOND, 5)
    SPEND.parent.mkdir(parents=True, exist_ok=True)
    SPEND.write_text(json.dumps(ledger, indent=2))


def _check_budget() -> None:
    spent, cap = spent_this_month(), monthly_cap()
    if spent >= cap:
        raise OverBudget(f"The studio has used ${spent:.2f} of its ${cap:.2f} this month, so it stopped.")


class _NoWatermark:
    """Leaves the audio as the model made it (Alec's choice; ARI_STUDIO_WATERMARK=1 restores it)."""

    def apply_watermark(self, wav, sample_rate):  # noqa: ANN001, ARG002
        return wav


def _watermark_wanted() -> bool:
    """Chatterbox marks its audio, inaudibly, as AI-generated. Off unless ARI_STUDIO_WATERMARK=1.

    Either way, label the post as AI-generated where the platform asks.
    """
    value = os.environ.get("ARI_STUDIO_WATERMARK") or _env_value("ARI_STUDIO_WATERMARK")
    return value == "1"


def _mps() -> bool:
    try:
        import torch

        return torch.backends.mps.is_available()
    except Exception:  # noqa: BLE001
        return False


def _duration(path: Path) -> float:
    """Seconds of audio. ffprobe, because the model writes float WAVs Python's wave can't read."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


# --- Shots and captions, drawn by Chrome ---------------------------------------------

STYLE = """
* { box-sizing: border-box; margin: 0; }
html, body { width: 1080px; height: 1920px; }
body { font-family: -apple-system, "SF Pro Display", "Helvetica Neue", sans-serif; color: #f4f4f6; }
"""


def _card(work: Path, name: str, *, day: int, big: str, label: str, bird: bool = False) -> Path:
    art = PET_ART / "sit.png"
    bird_html = f'<img src="file://{art}" style="width:520px;margin-top:80px">' if bird and art.exists() else ""
    page = f"""<style>{STYLE}
body {{ background: radial-gradient(120% 80% at 50% 20%, #1d2030 0%, #0c0d12 60%); display:flex; flex-direction:column;
  justify-content:center; padding: 0 96px; }}
.label {{ color:#ff5fa2; font-size:40px; font-weight:700; letter-spacing:6px; }}
.big {{ margin-top:36px; font-size:92px; font-weight:800; line-height:1.08; letter-spacing:-1px; }}
</style><div class="label">{html.escape(label)}</div><div class="big">{html.escape(big)}</div>{bird_html}"""
    return _render(work, name, page)


def _code_shots(date: str | None, count: int, work: Path) -> list[Path]:
    """Real diffs from the day's commits in ARI's public repository."""
    repo = _source_repo()
    if repo is None or not date or count == 0:
        return []
    shas = _git(repo, "log", "--all", f"--since={date} 00:00", f"--until={date} 23:59:59", "--format=%H %s").splitlines()
    shots = []
    for index, row in enumerate(shas[:count]):
        sha, _, subject = row.partition(" ")
        diff = _git(repo, "show", "--format=", "--unified=1", "--no-color", sha, "--", "*.py", "*.ts", "*.tsx", "*.swift")
        added = [line for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
        if not added:
            continue
        body = "".join(
            f'<div class="{"add" if line.startswith("+") else "del"}">{html.escape(line[:58])}</div>'
            for line in added[:CODE_LINES]
        )
        page = f"""<style>{STYLE}
body {{ background:#0c0d12; display:flex; flex-direction:column; justify-content:center; padding:0 64px; }}
.subject {{ color:#a2a7b4; font-size:38px; margin-bottom:40px; line-height:1.3; }}
.code {{ background:#151821; border-radius:28px; padding:44px 40px; font: 30px/1.55 ui-monospace, Menlo, monospace; }}
.add {{ color:#7ee2b8; white-space:pre; overflow:hidden; }} .del {{ color:#ff8a8a; white-space:pre; overflow:hidden; opacity:.7 }}
</style><div class="subject">{html.escape(subject)}</div><div class="code">{body}</div>"""
        shots.append(_render(work, f"code{index}", page))
    return shots


def _captions(lines: list[Line], work: Path) -> list[tuple[Path, float, float]]:
    """(image, start, end) for each caption, two to four words, spread across each line."""
    captions, start = [], 0.0
    for index, line in enumerate(lines):
        words = line.text.split()
        chunks = [" ".join(words[i : i + WORDS_PER_CAPTION]) for i in range(0, len(words), WORDS_PER_CAPTION)]
        spoken = line.seconds - PAUSE_SECONDS
        total = sum(len(chunk) for chunk in chunks) or 1
        at = start
        for number, chunk in enumerate(chunks):
            length = spoken * len(chunk) / total
            page = f"""<style>{STYLE}
body {{ background: transparent; display:flex; align-items:flex-end; justify-content:center; padding-bottom:520px; }}
.cap {{ font-size:84px; font-weight:900; text-align:center; text-transform:uppercase; color:#fff;
  -webkit-text-stroke: 4px #000; paint-order: stroke fill; max-width:920px; line-height:1.1; }}
</style><div class="cap">{html.escape(chunk)}</div>"""
            captions.append((_render(work, f"cap{index:02d}_{number:02d}", page, transparent=True), at, at + length))
            at += length
        start += line.seconds
    return captions


def _render(work: Path, name: str, page: str, transparent: bool = False) -> Path:
    source = work / f"{name}.html"
    source.write_text(f"<!doctype html><meta charset='utf-8'>{page}", encoding="utf-8")
    image = work / f"{name}.png"
    command = [
        str(CHROME), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
        f"--window-size={WIDTH},{HEIGHT}", f"--screenshot={image}", f"file://{source}",
    ]
    if transparent:
        command.insert(-1, "--default-background-color=00000000")
    subprocess.run(command, check=True, capture_output=True, timeout=60)
    return image


# --- The cut -------------------------------------------------------------------------


def _cut(lines: list[Line], captions: list[tuple[Path, float, float]], work: Path, day: int) -> Path:
    segments = []
    for index, line in enumerate(lines):
        frames = max(1, round(line.seconds * FPS))
        segment = work / f"seg{index:02d}.mp4"
        # A slow push in on each shot keeps stills alive.
        zoom = f"zoompan=z='min(zoom+0.0006,1.08)':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
        _ffmpeg("-loop", "1", "-i", str(line.shot), "-vf", f"scale={WIDTH * 2}:-1,{zoom}", "-frames:v", str(frames),
                "-pix_fmt", "yuv420p", str(segment))
        segments.append(segment)
    video = work / "video.mp4"
    listing = work / "segments.txt"
    listing.write_text("".join(f"file '{segment}'\n" for segment in segments))
    _ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(video))

    audio = work / "narration.wav"
    pause = work / "pause.wav"
    _ffmpeg("-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono", "-t", str(PAUSE_SECONDS), str(pause))
    parts = work / "audio.txt"
    parts.write_text("".join(f"file '{line.audio}'\nfile '{pause}'\n" for line in lines))
    _ffmpeg("-f", "concat", "-safe", "0", "-i", str(parts), "-ar", "48000", str(audio))

    inputs, chain, last = ["-i", str(video), "-i", str(audio)], [], "[0:v]"
    for number, (image, start, end) in enumerate(captions):
        inputs += ["-i", str(image)]
        tag = f"[v{number}]"
        chain.append(f"{last}[{number + 2}:v]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'{tag}")
        last = tag
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"day-{day}.mp4"
    script = work / "filter.txt"
    script.write_text(";".join(chain))
    _ffmpeg(*inputs, "-filter_complex_script", str(script), "-map", last, "-map", "1:a", "-c:v", "libx264",
            "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out))
    return out


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


# --- ARI -----------------------------------------------------------------------------


def _content_item(day_number: int) -> dict:
    listing = json.loads(subprocess.run([str(ARI_CLI), "api", "content", "list", "--json"], capture_output=True, text=True, check=True).stdout)
    for item in listing["items"]:
        if item.get("dayNumber") == day_number:
            return item
    raise SystemExit(f"There's no Day {day_number} in ARI's content library.")


def _source_repo() -> Path | None:
    value = os.environ.get("ARI_SOURCE_REPO") or _env_value("ARI_SOURCE_REPO")
    return Path(value) if value and Path(value).is_dir() else None


def _env_value(key: str) -> str | None:
    """A setting from ~/ARI/ari.env, which the studio reads without ARI's runtime."""
    env = ARI_HOME / "ari.env"
    if not env.exists():
        return None
    for line in env.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False).stdout


def main() -> int:
    parser = argparse.ArgumentParser(prog="ari-studio")
    commands = parser.add_subparsers(dest="command", required=True)
    produce_parser = commands.add_parser("produce", help="Make a building day's video.")
    produce_parser.add_argument("--day", type=int, required=True)
    produce_parser.add_argument("--script", type=int, default=1, help="Which outline, if the day has two.")
    produce_parser.add_argument("--keep", action="store_true", help="Keep the working files, for checking.")
    produce_parser.add_argument("--attach", action="store_true", help="Attach the video to the day in ARI's library.")
    args = parser.parse_args()
    out = produce(args.day, args.script, keep=args.keep)
    voice = "Alec (cloned)" if VOICE_SAMPLE.exists() else "default voice"
    print(f"Studio spend this month: ${spent_this_month():.2f} of ${monthly_cap():.2f}")
    if args.attach:
        subprocess.run(
            [str(ARI_CLI), "api", "content", "video", "--id", f"day-{args.day}", "--path", str(out), "--voice", voice],
            check=True, capture_output=True,
        )
    print(f"{out} ({voice})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
