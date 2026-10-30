from __future__ import annotations

import os
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

from ari_core.build_story import building_days, gather, latest_lessons, run_story
from ari_memory import create_engine, create_session_factory

NOW = datetime(2026, 10, 29, 22, 0, tzinfo=UTC)
WRITTEN = {
    "lessons": ["Mac control got used the first night.", "Reviews failed silently for a day."],
    "story": "Alec wanted to run his Mac from his phone. ARI learned to.",
    "scripts": [{"hook": "I text my laptop and it obeys.", "beats": ["The problem", "The build"], "caption": "Day 2 of building ARI."}],
}


def _commit(repo: Path, name: str, message: str, when: str) -> None:
    (repo / name).write_text(name)
    env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    subprocess.run(["git", "-C", str(repo), "add", name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", message], check=True, env=env)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    _commit(repo, "a.py", "feat: scaffold ARI", "2026-04-10T12:00:00")
    _commit(repo, "b.py", "feat(mac): phone controls the Mac\n\nHe wanted a remote.\n\nCo-Authored-By: X <x@y>", "2026-10-28T12:00:00")
    _commit(repo, "c.py", "fix(reviews): reviews get written", "2026-10-28T15:00:00")
    return repo


def test_days_are_numbered_by_building_day_from_the_first_commit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert building_days(repo) == [date(2026, 4, 10), date(2026, 10, 28)]
    facts = gather(repo, date(2026, 10, 28))
    assert facts["day"] == 2
    assert facts["commits"][0] == {"what": "feat(mac): phone controls the Mac", "why": "He wanted a remote."}
    assert gather(repo, date(2026, 10, 27)) is None


def test_a_day_becomes_a_story_with_lessons_first_and_is_kept_as_a_note(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    spine = tmp_path / "spine.db"
    seen: list[dict] = []

    def write(facts):
        seen.append(facts)
        return WRITTEN, None

    factory = create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))
    with factory() as session:
        story = run_story(session, repo=repo, day=date(2026, 10, 28), now=NOW, write=write, spine_db_path=spine)
        assert run_story(session, repo=repo, day=date(2026, 10, 27), now=NOW, write=write, spine_db_path=spine) is None

    assert seen[0]["day"] == 2 and len(seen) == 1
    assert story is not None and story.title == "Build story, Day 2 (Oct 28)"
    assert story.note().startswith("What ARI learned\n- Mac control got used")
    assert "Hook: I text my laptop and it obeys." in story.message()
    assert latest_lessons(spine) == WRITTEN["lessons"]
