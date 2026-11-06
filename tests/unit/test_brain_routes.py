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


def _ambient_seed(session_factory, *, loops: list[tuple[str, str]] = (), build: tuple[str, str] | None = None) -> None:
    from datetime import UTC, datetime, timedelta

    from ari_core.builds import propose_build
    from ari_core.state import CreateOpenLoopInput, create_open_loop
    from ari_memory.tables import BuildProposalRow

    start = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
    with session_factory() as session:
        for offset, (title, priority) in enumerate(loops):
            create_open_loop(
                session,
                loop=CreateOpenLoopInput(title=title, source="test", priority=priority),
                opened_at=start + timedelta(minutes=offset),
            )
        if build is not None:
            proposed, _ = propose_build(session, title=build[0], why="", brief="", now=start)
            session.get(BuildProposalRow, proposed.id).status = build[1]
        session.commit()


def test_ambient_status_is_idle_on_the_most_important_loop(harness) -> None:
    client, session_factory, _, _ = harness
    _ambient_seed(session_factory, loops=[("Water plants", "low"), ("Finish assignment", "high"), ("Call Kyle", "high")])

    body = client.get("/ambient/status").json()

    assert body["state"] == "idle"
    assert body["activity"] == "Finish assignment"  # highest priority, then oldest
    assert body["queue"] == 3
    assert set(body) == {"state", "activity", "queue", "updatedAt"}  # nothing private rides along


def test_ambient_status_shows_what_ari_is_building_and_pause_wins(harness) -> None:
    client, session_factory, _, _ = harness
    _ambient_seed(session_factory, loops=[("Finish assignment", "high")], build=("Email digest", "building"))

    assert client.get("/ambient/status").json()["activity"] == "Building: Email digest"

    pause_module.pause("Focus time")
    body = client.get("/ambient/status").json()
    assert (body["state"], body["activity"]) == ("paused", "Focus time")


def test_ambient_status_is_readable_from_the_screensaver_only(harness) -> None:
    client, _, _, _ = harness

    from_file_page = client.get("/ambient/status", headers={"Origin": "null"})
    from_a_website = client.get("/ambient/status", headers={"Origin": "https://example.com"})

    assert from_file_page.headers["access-control-allow-origin"] == "null"
    assert "access-control-allow-origin" not in from_a_website.headers
    assert from_file_page.json() == {**from_file_page.json(), "state": "idle", "activity": "", "queue": 0}
