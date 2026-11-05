from __future__ import annotations

from pathlib import Path

import pytest
from ari_core.modules.self_documentation.library import edit_script, get_content_item, set_status, store_build_day
from ari_core.script_review import review, rule_checks
from ari_memory import create_engine, create_session_factory

GOOD = {
    "hook": "My AI wrote two reviews and both were empty.",
    "beats": [
        "Every night ARI is supposed to review its own day.",
        "Two nights in a row, nothing arrived, and nothing said why.",
        "The model spent its whole budget thinking and wrote nothing.",
        "Now reviews get room to write, and a failure says so in the log.",
    ],
    "caption": "Day 23 of building ARI. A silent failure looks like success.",
}


def _setup(tmp_path: Path):
    spine = tmp_path / "spine.db"
    store_build_day(day_number=23, day_date="2026-10-29", title="Build story, Day 23 (Oct 29)", lessons=[],
                    story="", scripts=[dict(GOOD)], commit_count=1, db_path=spine)
    factory = create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))
    return spine, factory


def _editor(passed: bool, truth: list[str] | None = None):
    seen: list[dict] = []

    def write(facts):
        seen.append(facts)
        return {"passed": passed, "truth_problems": truth or [], "notes": ["Tighten beat 2."], "hook_score": 4,
                "flow_score": 4}, None

    return write, seen


def test_a_script_needs_a_passing_review_of_its_current_version_to_be_approved(tmp_path: Path) -> None:
    spine, factory = _setup(tmp_path)
    with pytest.raises(ValueError, match="needs ARI's review"):
        set_status("day-23", "script", db_path=spine)

    write, seen = _editor(passed=True)
    with factory() as session:
        reviewed = review(session, "day-23", repo=None, write=write, db_path=spine)
    assert reviewed.review["passed"] and seen[0]["day"] == 23 and seen[0]["scripts"][0]["hook"] == GOOD["hook"]
    assert reviewed.to_dict()["reviewCurrent"]

    edit_script("day-23", 0, hook=GOOD["hook"] + " Really.", beats=GOOD["beats"], caption=GOOD["caption"], db_path=spine)
    assert not get_content_item("day-23", db_path=spine).to_dict()["reviewCurrent"]
    with pytest.raises(ValueError, match="needs ARI's review"):
        set_status("day-23", "script", db_path=spine)  # the passed version is gone


def test_truth_problems_or_broken_rules_fail_a_review_the_editor_liked(tmp_path: Path) -> None:
    spine, factory = _setup(tmp_path)
    write, _ = _editor(passed=True, truth=["Alec never texted ARI to turn off the screen."])
    with factory() as session:
        item = review(session, "day-23", repo=None, write=write, db_path=spine)
    assert not item.review["passed"] and item.review["truth"]

    edit_script("day-23", 0, hook=GOOD["hook"], beats=GOOD["beats"][:2], caption="Look at this.", db_path=spine)
    problems = rule_checks(get_content_item("day-23", db_path=spine))
    assert any("2 beats" in problem for problem in problems)
    assert any("Day 23 of building ARI" in problem for problem in problems)


def test_editing_an_approved_script_sends_it_back_to_idea_and_production_locks_the_words(tmp_path: Path) -> None:
    spine, factory = _setup(tmp_path)
    write, _ = _editor(passed=True)
    with factory() as session:
        review(session, "day-23", repo=None, write=write, db_path=spine)
    set_status("day-23", "script", db_path=spine)
    edited = edit_script("day-23", 0, hook="New hook.", beats=GOOD["beats"], caption=GOOD["caption"], db_path=spine)
    assert edited.status == "idea" and edited.scripts[0]["by"] == "alec" and edited.hook == "New hook."
    with factory() as session:
        review(session, "day-23", repo=None, write=write, db_path=spine)
    set_status("day-23", "script", db_path=spine)
    set_status("day-23", "production", db_path=spine)
    with pytest.raises(ValueError, match="step it back"):
        edit_script("day-23", 0, hook="Late change.", beats=GOOD["beats"], caption=GOOD["caption"], db_path=spine)
