from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from ari_core.build_log import commits_between, recent_builds, record_release, tool_use
from ari_core.self_review import gather
from ari_memory import create_engine, create_session_factory
from ari_memory.tables import SkillInvocationRow

NOW = datetime(2026, 10, 28, 20, 0, tzinfo=UTC)


def _commit(repo: Path, name: str, message: str) -> str:
    (repo / name).write_text(name)
    subprocess.run(["git", "-C", str(repo), "add", name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", message], check=True)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, list[str]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    shas = [
        _commit(repo, "a.py", "feat: first\n\nWhy it was first."),
        _commit(repo, "b.py", "feat(mac): phone controls the Mac\n\nAlec wanted a remote.\n\nCo-Authored-By: X <x@y>"),
        _commit(repo, "c.py", "feat(email): ARI reads Gmail"),
    ]
    return repo, shas


def test_a_release_records_the_commits_since_the_last_one_in_their_own_words(tmp_path: Path) -> None:
    repo, shas = _repo(tmp_path)
    commits, files = commits_between(repo, shas[0], shas[2])
    assert [commit["subject"] for commit in commits] == ["feat(mac): phone controls the Mac", "feat(email): ARI reads Gmail"]
    assert commits[0]["body"] == "Alec wanted a remote."
    assert files == ["b.py", "c.py"]
    first, first_files = commits_between(repo, None, shas[0])
    assert [commit["subject"] for commit in first] == ["feat: first"] and first_files == ["a.py"]


def test_log_is_recorded_once_and_reviews_read_it_with_tool_use(tmp_path: Path) -> None:
    repo, shas = _repo(tmp_path)
    factory = create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))
    commits, files = commits_between(repo, shas[0], shas[2])
    with factory() as session:
        assert record_release(session, release="r1", commit=shas[2], commits=commits, files=files, shipped_at=NOW)
        assert record_release(session, release="r1", commit=shas[2], commits=commits, files=files, shipped_at=NOW) is None
        for tool in ("mac_open", "mac_open", "email_search"):
            session.add(SkillInvocationRow(
                id=uuid4(), occurred_at=NOW - timedelta(hours=1), channel="imessage", skill_kind="native",
                skill_name="brain", tool_name=tool, summary="", payload={}, is_error=False,
            ))
        session.commit()

        shipped = recent_builds(session, since=NOW - timedelta(days=1))
        assert shipped[0]["changes"][1] == {"what": "feat(email): ARI reads Gmail", "why": ""}
        assert tool_use(session, since=NOW - timedelta(days=7)) == {"mac_open": 2, "email_search": 1}

        facts = gather(session, kind="night", now=NOW + timedelta(minutes=5), apple=None)
        assert facts["shipped_recently"][0]["release"] == "r1"
        assert facts["tool_use_last_week"]["mac_open"] == 2
