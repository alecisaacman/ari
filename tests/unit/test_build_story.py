from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from ari_core.build_log import record_release
from ari_core.build_story import latest_lessons, run_story
from ari_memory import create_engine, create_session_factory

NOW = datetime(2026, 11, 1, 19, 0, tzinfo=UTC)
WRITTEN = {
    "lessons": ["Mac control got used the first night.", "Reviews failed silently for a day."],
    "story": "Alec wanted to run his Mac from his phone. ARI learned to.",
    "scripts": [{"hook": "I text my laptop and it obeys.", "beats": ["The problem", "The build"], "caption": "Day 3."}],
}


def _factory(tmp_path: Path):
    return create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))


def test_the_week_becomes_a_story_with_lessons_first_and_is_kept_as_a_note(tmp_path: Path) -> None:
    seen: list[dict] = []

    def write(facts):
        seen.append(facts)
        return WRITTEN, None

    spine = tmp_path / "spine.db"
    with _factory(tmp_path)() as session:
        commits = [{"sha": "abc1234", "subject": "feat(mac): phone controls the Mac", "body": "He wanted a remote."}]
        record_release(session, release="r1", commit="abc1234", commits=commits, files=["mac.py"], shipped_at=NOW - timedelta(days=1))
        story = run_story(session, now=NOW, write=write, spine_db_path=spine)

    assert seen[0]["shipped"][0]["changes"][0]["why"] == "He wanted a remote."
    assert story is not None and story.title == "Build story, week of Oct 26"
    assert story.note().startswith("What ARI learned\n- Mac control got used")
    assert "I text my laptop and it obeys." in story.message()
    assert latest_lessons(spine) == WRITTEN["lessons"]


def test_no_story_when_nothing_shipped(tmp_path: Path) -> None:
    with _factory(tmp_path)() as session:
        assert run_story(session, now=NOW, write=lambda facts: (WRITTEN, None), spine_db_path=tmp_path / "s.db") is None
