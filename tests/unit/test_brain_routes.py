from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ari_api.brain_routes import register_brain_routes
from ari_core import brain_usage
from ari_core.brain import BrainResponse
from ari_core.core import pause as pause_module
from ari_core.modules.memory.db import remember_ari_memory
from ari_core.reminders import set_reminder
from ari_memory import create_engine, create_session_factory
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pause_module, "PAUSED_MARKER_PATH", tmp_path / ".paused")
    monkeypatch.setattr(brain_usage, "_budget_file", lambda: tmp_path / "brain-budget.json")
    monkeypatch.delenv("ARI_BRAIN_MONTHLY_BUDGET_USD", raising=False)
    session_factory = create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))
    spine = tmp_path / "spine.db"
    heard: list[str] = []

    def brain(*, text: str, history: list[dict[str, Any]], **_: Any) -> BrainResponse:
        heard.append(text)
        reply = f"Heard: {text}"
        return BrainResponse(
            reply=reply,
            messages=[*history, {"role": "user", "content": text}, {"role": "assistant", "content": [{"type": "text", "text": reply}]}],
        )

    app = FastAPI()
    register_brain_routes(app, session_factory, action_desk=lambda: None, respond=brain, spine_db_path=lambda: spine)
    return TestClient(app), session_factory, spine, heard


def test_hub_messages_reach_aris_brain_and_keep_one_conversation(harness) -> None:
    client, _, _, heard = harness

    first = client.post("/brain/messages", json={"text": "what's on my plate?"}).json()
    second = client.post("/brain/messages", json={"text": "and tomorrow?"}).json()

    assert heard == ["what's on my plate?", "and tomorrow?"]
    assert first["reply"] == "Heard: what's on my plate?"
    assert [line["text"] for line in second["conversation"]] == [
        "what's on my plate?",
        "Heard: what's on my plate?",
        "and tomorrow?",
        "Heard: and tomorrow?",
    ]


def test_hub_commands_are_decided_without_the_model(harness) -> None:
    client, _, _, heard = harness

    paused = client.post("/brain/messages", json={"text": "ARI stop"}).json()
    ignored = client.post("/brain/messages", json={"text": "hello?"}).json()

    assert paused["reply"].startswith("Paused.")
    assert ignored["reply"] is None
    assert heard == []


def test_panel_shows_what_is_inside_ari(harness) -> None:
    from datetime import UTC, datetime, timedelta

    client, session_factory, spine, _ = harness
    remember_ari_memory("person", "Sam (internship contact)", "Works at Ramp.", db_path=spine)
    now = datetime.now(tz=UTC)
    with session_factory() as session:
        set_reminder(session, text="Call Sam", remind_at=now + timedelta(hours=1), now=now)
    client.post("/brain/messages", json={"text": "remember Sam"})

    panel = client.get("/brain/panel").json()

    assert [memory["title"] for memory in panel["memories"]] == ["Sam (internship contact)"]
    assert [reminder["text"] for reminder in panel["reminders"]] == ["Call Sam"]
    assert panel["conversations"]["hub"][-1] == {"role": "ari", "text": "Heard: remember Sam"}
    assert panel["paused"]["paused"] is False
    assert set(panel) >= {"today", "week", "openLoops", "alerts", "spend", "waitingForApproval", "notes"}
