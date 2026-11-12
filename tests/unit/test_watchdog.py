from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from ari_core.builds import SHIPPING, decide_build, propose_build
from ari_core.watchdog import RECORDS, Problem, Watchdog, check_records
from ari_memory import create_engine, create_session_factory
from ari_memory.tables import BuildProposalRow

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=UTC)
GET_DONE = Problem(key="get-done", text="I can't read GET DONE.", label="Reading GET DONE", after=timedelta(minutes=30))


def _send_all(watchdog: Watchdog, problems: list[Problem], *, now: datetime, cleared: set[str] | None = None) -> list[str]:
    notices = watchdog.observe(problems, cleared=cleared or set(), now=now)
    for notice in notices:
        watchdog.told(notice)
    return [notice.body for notice in notices]


def test_a_lasting_problem_is_told_once_after_it_lasts_and_again_when_it_clears(tmp_path: Path) -> None:
    watchdog = Watchdog(tmp_path / "watchdog.json")
    assert _send_all(watchdog, [GET_DONE], now=NOW) == []  # might be a blip
    assert _send_all(watchdog, [GET_DONE], now=NOW + timedelta(minutes=31)) == ["I can't read GET DONE."]
    assert _send_all(watchdog, [GET_DONE], now=NOW + timedelta(hours=2)) == []  # told once
    assert _send_all(watchdog, [], now=NOW + timedelta(hours=3)) == []  # its source didn't run: not cleared
    assert _send_all(watchdog, [], now=NOW + timedelta(hours=3), cleared={"get-done"}) == [
        "Reading GET DONE is working again."
    ]
    assert _send_all(watchdog, [], now=NOW + timedelta(hours=4), cleared={"get-done"}) == []


def test_a_blip_that_clears_itself_is_never_texted(tmp_path: Path) -> None:
    watchdog = Watchdog(tmp_path / "watchdog.json")
    assert _send_all(watchdog, [GET_DONE], now=NOW) == []
    assert _send_all(watchdog, [], now=NOW + timedelta(minutes=5), cleared={"get-done"}) == []
    assert _send_all(watchdog, [GET_DONE], now=NOW + timedelta(minutes=40)) == []  # a new start, not 40 minutes


def test_a_one_off_failure_waits_until_it_can_be_sent(tmp_path: Path) -> None:
    watchdog = Watchdog(tmp_path / "watchdog.json")
    review = Problem(key="review-night-2026-11-10", text="The night review didn't get written.", lasting=False)
    assert [notice.body for notice in watchdog.observe([review], cleared=set(), now=NOW)] == [review.text]
    # Not sent (quiet hours): it's still waiting on the next poll, without being reported again.
    assert [notice.body for notice in watchdog.observe([], cleared=set(), now=NOW + timedelta(hours=9))] == [review.text]
    assert _send_all(watchdog, [], now=NOW + timedelta(hours=9)) == [review.text]
    assert _send_all(watchdog, [], now=NOW + timedelta(hours=10)) == []


def test_a_damaged_state_file_starts_over_instead_of_failing(tmp_path: Path) -> None:
    path = tmp_path / "watchdog.json"
    path.write_text("{not json")
    assert Watchdog(path).observe([], cleared=set(), now=NOW) == []


def _factory(tmp_path: Path):
    return create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))


def test_a_ship_that_never_finishes_is_told_after_thirty_minutes_and_cleared_when_it_does(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    watchdog = Watchdog(tmp_path / "watchdog.json")
    with factory() as session:
        build, _ = propose_build(session, title="Email digest", why="", brief="", now=NOW)
        decide_build(session, build.id, "approve", now=NOW)
        row = session.get(BuildProposalRow, build.id)
        row.status = SHIPPING
        session.commit()

        def poll(now: datetime) -> list[str]:
            records = check_records(session, now=now, builder_on=True)
            return _send_all(watchdog, records, now=now, cleared={RECORDS})

        assert poll(NOW) == []  # shipping normally takes minutes
        [told] = poll(NOW + timedelta(minutes=31))
        assert "“Email digest” has been shipping" in told and "builder.log" in told
        row.status = "done"
        session.commit()
        assert poll(NOW + timedelta(minutes=40)) == ["Shipping “Email digest” is working again."]


def test_an_approved_build_nobody_picked_up_is_told_with_the_likely_reason(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        build, _ = propose_build(session, title="Email digest", why="", brief="", now=NOW)
        decide_build(session, build.id, "approve", now=NOW)
        assert check_records(session, now=NOW + timedelta(hours=20), builder_on=True) == []  # tonight's run is coming
        [waiting] = check_records(session, now=NOW + timedelta(hours=31), builder_on=True)
        assert "31 hours ago" in waiting.text and "Claude app" in waiting.text
        [off] = check_records(session, now=NOW + timedelta(hours=31), builder_on=False)
        assert "connect-builds" in off.text


def _spend(session, channel: str, dollars: float, at: datetime) -> None:
    from uuid import uuid4

    from ari_memory.tables import BrainUsageRow

    session.add(BrainUsageRow(
        id=uuid4(), occurred_at=at, channel=channel, model="m", input_tokens=1, output_tokens=1,
        cache_write_tokens=0, cache_read_tokens=0, web_searches=0, cost_microusd=int(dollars * 1e6), escalated=True,
    ))
    session.commit()


def test_a_costly_day_and_an_unknown_spender_are_each_told_once(tmp_path: Path) -> None:
    from ari_core.watchdog import check_spend

    watchdog = Watchdog(tmp_path / "watchdog.json")
    with _factory(tmp_path)() as session:
        _spend(session, "review", 0.03, NOW - timedelta(minutes=5))
        assert check_spend(session, now=NOW) == []  # a normal day
        _spend(session, "story", 0.40, NOW - timedelta(minutes=4))
        _spend(session, "mystery_loop", 0.001, NOW - timedelta(minutes=3))
        told = _send_all(watchdog, check_spend(session, now=NOW), now=NOW)
        assert len(told) == 2
        assert "$0.43 of API credits today" in told[0] and "story $0.40" in told[0]
        assert "mystery_loop" in told[1]
        # The check runs every poll; Alec hears each once.
        assert _send_all(watchdog, check_spend(session, now=NOW + timedelta(minutes=1)), now=NOW) == []
