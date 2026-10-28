from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ari_core import brain
from ari_core.apple import AppleDesk, AppleError
from ari_memory import create_engine, create_session_factory


class FakeEventKit:
    """Stands in for tools/ari-eventkit: Alec's real lists are never touched by tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.reminders: dict[str, dict[str, Any]] = {}

    def __call__(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((command, payload))
        if command == "add-reminder":
            item = {"id": f"r{len(self.reminders) + 1}", "list": payload["list"], "title": payload["title"]}
            if "due" in payload:
                item["due"] = payload["due"]
            self.reminders[item["id"]] = item
            return {"reminder": item}
        if command == "reminders":
            return {"reminders": [item for item in self.reminders.values() if item["list"] == payload["list"]]}
        if command in {"complete-reminder", "remove-reminder"}:
            if payload["id"] not in self.reminders:
                raise AppleError("That reminder isn't in Reminders anymore.")
            return {"reminder": self.reminders.pop(payload["id"])}
        if command == "events":
            return {"events": [{"title": "Office hours", "start": payload["start"], "calendar": "Work"}]}
        if command == "add-event":
            return {"event": {"id": "e1", **payload}}
        raise AssertionError(command)


def _dispatcher(tmp_path, apple: AppleDesk | None):
    session_factory = create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))
    return brain.make_tool_dispatcher(
        session_factory, save_for_later=lambda link, note: None, spine_db_path=tmp_path / "spine.db", apple=apple
    )


def test_ari_writes_to_get_done_and_checks_items_off(tmp_path) -> None:
    eventkit = FakeEventKit()
    dispatch = _dispatcher(tmp_path, AppleDesk(run=eventkit))

    added = dispatch("add_to_get_done", {"title": "Buy the e-bike", "due": "2026-11-02T09:00"})["added"]
    assert added["list"] == "GET DONE"
    assert added["due"].startswith("2026-11-02T")
    assert [item["title"] for item in dispatch("get_done_list", {})["get_done"]] == ["Buy the e-bike"]
    assert dispatch("complete_get_done", {"reminder_id": added["id"]})["completed"]["title"] == "Buy the e-bike"
    assert "error" in dispatch("complete_get_done", {"reminder_id": added["id"]})
    assert {payload.get("list") for command, payload in eventkit.calls if "list" in payload} == {"GET DONE"}


def test_timed_reminder_goes_to_get_done_and_is_removed_when_cancelled(tmp_path) -> None:
    eventkit = FakeEventKit()
    dispatch = _dispatcher(tmp_path, AppleDesk(run=eventkit))
    at = (datetime.now() + timedelta(hours=2)).replace(microsecond=0).isoformat()

    reminder = dispatch("set_reminder", {"text": "Call Sam", "at": at})["reminder"]
    assert reminder["delivered_by"] == "Apple Reminders (GET DONE)"
    assert [item["title"] for item in eventkit.reminders.values()] == ["Call Sam"]
    dispatch("cancel_reminder", {"reminder_id": reminder["id"]})
    assert eventkit.reminders == {}


def test_reminder_falls_back_to_a_text_when_apple_refuses(tmp_path) -> None:
    def refuse(command: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise AppleError("ARI doesn't have access to Reminders.")

    dispatch = _dispatcher(tmp_path, AppleDesk(run=refuse))
    at = (datetime.now() + timedelta(hours=2)).replace(microsecond=0).isoformat()

    assert dispatch("set_reminder", {"text": "Call Sam", "at": at})["reminder"]["delivered_by"] == "ARI text"
    assert dispatch("get_done_list", {}) == {"error": "ARI doesn't have access to Reminders."}


def test_calendar_is_read_by_day_and_events_default_to_the_ari_calendar(tmp_path) -> None:
    eventkit = FakeEventKit()
    dispatch = _dispatcher(tmp_path, AppleDesk(run=eventkit))

    assert dispatch("get_calendar", {"start_date": "2026-10-28", "days": 90})["events"][0]["title"] == "Office hours"
    command, payload = eventkit.calls[-1]
    start, end = datetime.fromisoformat(payload["start"]), datetime.fromisoformat(payload["end"])
    assert command == "events" and end - start == timedelta(days=31)

    event = dispatch("add_calendar_event", {"title": "Study group", "start": "2026-10-29T18:00"})["added"]
    assert event["calendar"] == "ARI"
    duration = datetime.fromisoformat(event["end"]) - datetime.fromisoformat(event["start"])
    assert duration == timedelta(hours=1)


def test_without_a_connection_apple_tools_say_so(tmp_path) -> None:
    dispatch = _dispatcher(tmp_path, None)

    assert "aren't connected" in dispatch("get_done_list", {})["error"]
    at = datetime.now(tz=UTC) + timedelta(hours=1)
    assert dispatch("set_reminder", {"text": "Stretch", "at": at.isoformat()})["reminder"]["delivered_by"] == "ARI text"


def test_connection_is_off_unless_switched_on(monkeypatch, tmp_path) -> None:
    helper = tmp_path / "ari-eventkit"
    helper.write_text("")
    monkeypatch.setenv("ARI_EVENTKIT", str(helper))
    monkeypatch.delenv("ARI_APPLE_CONNECTED", raising=False)
    assert AppleDesk.connected() is None
    monkeypatch.setenv("ARI_APPLE_CONNECTED", "1")
    assert AppleDesk.connected() is not None
