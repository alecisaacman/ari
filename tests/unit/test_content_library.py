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


def test_days_move_from_draft_to_posted_and_list_newest_first(tmp_path: Path) -> None:
    spine = tmp_path / "spine.db"
    _day(spine, 16)
    _day(spine, 19)
    assert [item.item_id for item in list_content_items(db_path=spine)] == ["day-19", "day-16"]
    assert set_status("day-16", "ready", db_path=spine).status == "ready"
    posted = set_status("day-16", "posted", db_path=spine)
    assert posted.status == "posted" and posted.posted_at
    assert [item.item_id for item in list_content_items(status="draft", db_path=spine)] == ["day-19"]
    with pytest.raises(ValueError):
        set_status("day-19", "published", db_path=spine)


def test_the_idea_bank_reads_the_library_and_leaves_out_posted_days(tmp_path: Path) -> None:
    spine = tmp_path / "spine.db"
    _day(spine, 16)
    _day(spine, 19)
    set_status("day-19", "posted", db_path=spine)
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
    assert dispatch("get_content_library", {})["content"][0]["status"] == "draft"
    assert dispatch("set_content_status", {"day": 16, "status": "posted"})["updated"]["status"] == "posted"
    assert "no Day 3" in dispatch("set_content_status", {"day": 3, "status": "posted"})["error"]
