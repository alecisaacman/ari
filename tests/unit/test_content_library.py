from __future__ import annotations

from pathlib import Path

import pytest
from ari_core.brain import FAST_TOOLS, make_tool_dispatcher
from ari_core.modules.self_documentation.content_ideas import generate_content_idea_bank
from ari_core.modules.self_documentation.library import list_content_items, set_status, store_build_day

SCRIPTS = [
    {"hook": "I killed ARI mid-action and it did the same thing twice.", "beats": ["Crash", "Fix"], "caption": "Day 16."},
    {"hook": "Second angle.", "beats": ["One"], "caption": "Day 16."},
]


def _day(spine: Path, number: int, hook_prefix: str = "") -> None:
    scripts = [{**script, "hook": hook_prefix + script["hook"]} for script in SCRIPTS]
    store_build_day(day_number=number, day_date=f"2026-10-{number:02d}", title=f"Build story, Day {number}",
                    lessons=["A lesson."], story="The story.", scripts=scripts, commit_count=3, db_path=spine)


def _walk(spine: Path, item_id: str, *stages: str) -> None:
    for stage in stages:
        set_status(item_id, stage, db_path=spine)


def test_days_go_through_production_before_they_can_be_ready_or_posted(tmp_path: Path) -> None:
    spine = tmp_path / "spine.db"
    _day(spine, 16)
    _day(spine, 19)
    assert [item.item_id for item in list_content_items(db_path=spine)] == ["day-19", "day-16"]
    assert list_content_items(db_path=spine)[1].status == "idea"
    with pytest.raises(ValueError, match="can go to script or skipped"):
        set_status("day-16", "ready", db_path=spine)  # no finished video yet
    _walk(spine, "day-16", "script", "production", "ready")
    with pytest.raises(ValueError):
        set_status("day-16", "idea", db_path=spine)  # only one stage back at a time
    posted = set_status("day-16", "posted", db_path=spine)
    assert posted.status == "posted" and posted.posted_at
    assert [item.item_id for item in list_content_items(status="idea", db_path=spine)] == ["day-19"]
    with pytest.raises(ValueError):
        set_status("day-19", "published", db_path=spine)


def test_days_saved_as_drafts_before_production_existed_read_as_ideas(tmp_path: Path) -> None:
    from ari_core.modules.coordination.db import get_coordination_entity, put_coordination_entity

    spine = tmp_path / "spine.db"
    _day(spine, 16)
    row = dict(get_coordination_entity("content_item", "day-16", db_path=spine))
    put_coordination_entity("content_item", {**row, "status": "draft"}, db_path=spine)
    assert list_content_items(db_path=spine)[0].status == "idea"
    assert set_status("day-16", "script", db_path=spine).status == "script"


def test_the_idea_bank_reads_the_library_and_leaves_out_posted_days(tmp_path: Path) -> None:
    spine = tmp_path / "spine.db"
    _day(spine, 16)
    _day(spine, 19)
    set_status("day-19", "skipped", db_path=spine)
    bank = generate_content_idea_bank(db_path=spine)
    assert [idea.idea_id for idea in bank.ideas] == ["day-16-1", "day-16-2"]
    assert bank.ideas[0].suggested_shot_list == ("Crash", "Fix")
    assert "content library" in bank.source_of_truth


def test_ari_lists_and_marks_days_by_text(tmp_path: Path) -> None:
    assert {"get_content_library", "set_content_status"} <= {tool["name"] for tool in FAST_TOOLS}
    spine = tmp_path / "spine.db"
    _day(spine, 16)

    def no_session():
        raise AssertionError

    dispatch = make_tool_dispatcher(no_session, save_for_later=lambda link, note: None, spine_db_path=spine)
    assert dispatch("get_content_library", {})["content"][0]["status"] == "idea"
    assert dispatch("set_content_status", {"day": 16, "status": "script"})["updated"]["status"] == "script"
    assert "can go to production" in dispatch("set_content_status", {"day": 16, "status": "posted"})["error"]
    assert "no Day 3" in dispatch("set_content_status", {"day": 3, "status": "script"})["error"]


def test_the_api_lists_the_library_and_moves_items(tmp_path: Path) -> None:
    from ari_memory import create_engine, create_session_factory
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ari_api.brain_routes import register_brain_routes

    spine = tmp_path / "spine.db"
    _day(spine, 16)
    app = FastAPI()
    factory = create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))
    register_brain_routes(app, factory, action_desk=lambda: None, spine_db_path=lambda: spine, apple=lambda: None)
    client = TestClient(app)

    view = client.get("/content").json()
    assert view["counts"]["idea"] == 1 and view["items"][0]["scripts"][0]["beats"] == ["Crash", "Fix"]
    assert view["moves"]["production"] == ["ready", "script"]
    assert client.post("/content/day-16/status", json={"status": "script"}).json()["status"] == "script"
    assert client.post("/content/day-16/status", json={"status": "posted"}).status_code == 400
    assert client.post("/content/day-16/status", json={"status": "published"}).status_code == 400
    assert client.post("/content/day-99/status", json={"status": "ready"}).status_code == 404
