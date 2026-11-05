from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

STUDIO = Path(__file__).resolve().parents[2] / "tools" / "ari-studio" / "studio.py"


@pytest.fixture
def studio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    spec = importlib.util.spec_from_file_location("ari_studio", STUDIO)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "ari_studio", module)  # dataclasses look their module up
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "SPEND", tmp_path / "spend.json")
    monkeypatch.setattr(module, "ARI_HOME", tmp_path)
    monkeypatch.setattr(module, "VOICE_SAMPLE", tmp_path / "no-sample.wav")
    monkeypatch.setenv("REPLICATE_API_TOKEN", "test-token")
    monkeypatch.delenv("ARI_STUDIO_VOICE", raising=False)
    monkeypatch.delenv("ARI_STUDIO_MONTHLY_USD", raising=False)
    return module


def test_with_a_replicate_token_narration_runs_there(studio) -> None:
    assert studio._voice_backend() == "replicate"


def test_spend_is_counted_at_the_dearest_rate_and_the_cap_stops_the_studio(studio, monkeypatch) -> None:
    now = datetime(2026, 11, 5, tzinfo=UTC)
    studio._record_spend(1000, now=now)  # 1000 GPU seconds
    assert studio.spent_this_month(now) == pytest.approx(1.4)
    monkeypatch.setenv("ARI_STUDIO_MONTHLY_USD", "1.40")
    with pytest.raises(studio.OverBudget, match="stopped"):
        studio._check_budget()
    assert studio.spent_this_month(datetime(2026, 12, 1, tzinfo=UTC)) == 0  # a new month starts fresh


def test_each_line_is_narrated_downloaded_and_billed(studio, monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_replicate(method, path, body=None, wait=False):
        calls.append((method, path, body))
        if method == "POST":
            return {"id": "p1", "status": "processing"}
        return {"id": "p1", "status": "succeeded", "output": "https://replicate.delivery/x/out.wav",
                "metrics": {"predict_time": 10.0}}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"RIFF-audio"

    monkeypatch.setattr(studio, "_replicate", fake_replicate)
    monkeypatch.setattr(studio.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(studio.urllib.request, "urlopen", lambda url, timeout=0: Response())
    lines = [studio.Line("First line.", tmp_path / "a.png"), studio.Line("Second line.", tmp_path / "b.png")]

    studio._narrate_replicate(lines, tmp_path)

    posts = [body for method, path, body in calls if method == "POST"]
    assert [body["input"]["prompt"] for body in posts] == ["First line.", "Second line."]
    assert "audio_prompt" not in posts[0]["input"]  # no sample yet: the default voice
    assert lines[0].audio.read_bytes() == b"RIFF-audio"
    assert json.loads(studio.SPEND.read_text())[datetime.now(tz=UTC).strftime("%Y-%m")]["seconds"] == 20.0


def test_a_failed_line_is_still_billed_and_stops_the_video(studio, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(studio, "_replicate", lambda *a, **k: {"id": "p", "status": "failed", "error": "boom",
                                                                "metrics": {"predict_time": 5.0}})
    with pytest.raises(RuntimeError, match="boom"):
        studio._narrate_replicate([studio.Line("Hi.", tmp_path / "a.png")], tmp_path)
    assert studio.spent_this_month() == pytest.approx(0.007)


def test_beats_written_as_notes_are_spoken_as_sentences(studio) -> None:
    assert studio._spoken("Fix: 8000 tokens at low effort") == "The fix: 8000 tokens at low effort."
    assert studio._spoken("It works?") == "It works?"
