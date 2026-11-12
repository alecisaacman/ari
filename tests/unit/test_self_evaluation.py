from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from ari_core.builds import decide_build, list_builds
from ari_core.self_evaluation import announcement, evidence, propose, unannounced
from ari_memory import create_engine, create_session_factory
from ari_memory.tables import BrainUsageRow, SkillInvocationRow

NOW = datetime(2026, 11, 12, 6, 45, tzinfo=UTC)


def _factory(tmp_path: Path):
    return create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))


def test_evidence_shows_errors_spend_and_what_the_watchdog_has_open(tmp_path: Path) -> None:
    (tmp_path / "imessage").mkdir()
    watchdog = tmp_path / "imessage" / "watchdog.json"
    watchdog.write_text(json.dumps({"open": {"get-done": {"text": "I can't read GET DONE."}}, "pending": {}}))
    with _factory(tmp_path)() as session:
        session.add(SkillInvocationRow(
            id=uuid4(), occurred_at=NOW - timedelta(days=2), channel="imessage", skill_kind="native",
            skill_name="calendar", tool_name="calendar_delete", summary="Can't delete events.", payload={},
            is_error=True,
        ))
        session.add(BrainUsageRow(
            id=uuid4(), occurred_at=NOW - timedelta(hours=1), channel="review", model="m", input_tokens=1,
            output_tokens=1, cache_write_tokens=0, cache_read_tokens=0, web_searches=0, cost_microusd=17000,
            escalated=True,
        ))
        session.commit()
        facts = evidence(session, now=NOW, home=tmp_path)
    assert facts["tool_errors"] == ["calendar_delete: Can't delete events."]
    assert facts["api_spend_this_month_usd"] == {"review": 0.017}
    assert facts["watchdog_open"] == {"get-done": "I can't read GET DONE."}


def test_one_proposal_waits_for_alec_and_is_texted_once(tmp_path: Path) -> None:
    with _factory(tmp_path)() as session:
        first = propose(session, title="Delete calendar events", why="He asked twice this week.",
                        brief="Add a calendar_delete tool.", now=NOW)
        assert first == "proposed: Delete calendar events"
        # The next night, while he hasn't answered, nothing new piles up.
        assert propose(session, title="Other", why="", brief="", now=NOW + timedelta(days=1)).startswith(
            "not proposed: “Delete calendar events” is still waiting"
        )
        [row] = unannounced(session)
        assert "“Delete calendar events”. He asked twice this week." in announcement(row)
        row.announced_status = row.status
        session.commit()
        assert unannounced(session) == []
        decide_build(session, list_builds(session)[0].id, "approve", now=NOW + timedelta(hours=8))
        # Answered, so the next evaluation may propose again.
        assert propose(session, title="Other", why="x", brief="y", now=NOW + timedelta(days=1)) == "proposed: Other"


def test_the_audit_flags_a_part_that_went_quiet_even_without_an_error(tmp_path: Path) -> None:
    (tmp_path / "imessage").mkdir()
    local = NOW.astimezone()
    (tmp_path / "imessage" / "last-run").write_text((NOW - timedelta(minutes=2)).isoformat())
    (tmp_path / "imessage" / "last-review-morning").write_text(local.date().isoformat())
    (tmp_path / "imessage" / "last-review-night").write_text((local.date() - timedelta(days=4)).isoformat())
    with _factory(tmp_path)() as session:
        health = {check["part"]: check for check in evidence(session, now=NOW, home=tmp_path)["health"]}
    assert health["iMessage poller"]["ok"] and health["morning review"]["ok"]
    assert not health["night review"]["ok"]  # four days without one, and nothing logged an error
    assert not health["live release"]["ok"]
