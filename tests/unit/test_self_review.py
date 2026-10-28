from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ari_core import brain_usage
from ari_core.apple import AppleDesk
from ari_core.builds import list_builds
from ari_core.self_review import gather, run_review
from ari_memory import create_engine, create_session_factory

NOW = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)


def eventkit(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    if command == "reminders":
        return {"reminders": [{"id": "r1", "title": "Get a REAL ID"}]}
    if command == "completed":
        return {"reminders": [{"id": "r2", "title": "Request a replacement debit card"}]}
    if command == "events":
        return {"events": [{"title": "ECON 441", "start": payload["start"], "calendar": "School"}]}
    raise AssertionError(command)


def _session_factory(tmp_path):
    return create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))


def test_night_review_sees_what_got_done_and_tomorrow(tmp_path) -> None:
    with _session_factory(tmp_path)() as session:
        facts = gather(session, kind="night", now=NOW, apple=AppleDesk(run=eventkit))

    assert facts["checked_off_today"] == ["Request a replacement debit card"]
    assert facts["calendar_tomorrow"][0]["title"] == "ECON 441"
    assert facts["get_done"] == [{"title": "Get a REAL ID", "due": None}]
    assert any(skill["skill_id"] == "ari.native.email_calendar_triage" for skill in facts["skills_not_built"])


def test_review_proposes_one_build_and_never_twice(tmp_path) -> None:
    seen: list[dict[str, Any]] = []

    def write(kind: str, facts: dict[str, Any]):
        seen.append(facts)
        return {
            "message": "Today: ECON 441 at 5:30. Build email triage next? Approve or hold.",
            "build": {"title": "Email triage", "why": "You asked about email twice.", "brief": "Read Gmail.",
                      "skill_id": "ari.native.email_calendar_triage"},
        }, None

    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        first = run_review(session, kind="morning", now=NOW, apple=AppleDesk(run=eventkit), write=write,
                           spine_db_path=tmp_path / "spine.db")
        second = run_review(session, kind="night", now=NOW + timedelta(hours=6), apple=None, write=write,
                            spine_db_path=tmp_path / "spine.db")
        builds = list_builds(session)

    assert first is not None and first.build is not None and first.build["new"] is True
    assert second is not None and second.build is not None and second.build["new"] is False
    assert [build.title for build in builds] == ["Email triage"]
    assert seen[1]["build_list"][0]["title"] == "Email triage"
    assert seen[1]["apple"] == "Reminders and Calendar aren't connected."


def test_no_review_when_the_budget_is_used_up(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(brain_usage, "_budget_file", lambda: tmp_path / "budget.json")
    brain_usage.set_monthly_budget_usd(0)

    def write(kind: str, facts: dict[str, Any]):
        raise AssertionError("no model call without budget")

    with _session_factory(tmp_path)() as session:
        assert run_review(session, kind="morning", now=NOW, write=write) is None


def test_a_reply_that_isnt_json_is_still_sent_without_a_build(tmp_path) -> None:
    from ari_core.self_review import _parse

    assert _parse("Quiet day. Nothing due.") == {"message": "Quiet day. Nothing due.", "build": None}
    assert _parse('Here: {"message": "Hi", "build": null}')["message"] == "Hi"
