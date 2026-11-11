from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pytest
from ari_core import local_intents
from ari_core.apple import AppleDesk
from ari_core.local_intents import answer
from ari_core.mac import MacDesk

NOW = datetime(2026, 11, 10, 14, 0).astimezone()


class FakeEventKit:
    def __init__(self) -> None:
        self.items = [
            {"id": "r1", "title": "Get a REAL ID", "completed": False},
            {"id": "r2", "title": "Request a replacement debit card", "completed": False},
            {"id": "r3", "title": "Request transcripts", "completed": False},
        ]
        self.calls: list[str] = []

    def __call__(self, command: str, payload: dict) -> dict:
        self.calls.append(command)
        if command == "reminders":
            return {"reminders": list(self.items)}
        if command == "add-reminder":
            self.items.append({"id": "new", "title": payload["title"], "completed": False})
            return {"reminder": self.items[-1]}
        if command == "complete-reminder":
            item = next(i for i in self.items if i["id"] == payload["id"])
            item["completed"] = True
            return {"reminder": item}
        if command == "events":
            day = payload["start"][:10]
            return {"events": [
                {"title": "ECON 412", "start": f"{day}T13:00:00-08:00", "end": f"{day}T14:15:00-08:00", "all_day": False},
                {"title": "Tutoring", "start": f"{day}T15:00:00-08:00", "end": f"{day}T16:00:00-08:00", "all_day": False},
            ]}
        raise AssertionError(command)


class FakeMac:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str], timeout: float) -> str:
        self.calls.append(list(argv))
        if argv[:2] == ["shortcuts", "list"]:
            return "Put the fan on auto\nOpen ARI Hub\n"
        if argv[:2] == ["lsappinfo", "visibleProcessList"]:
            return 'ASN:0x0-0x1-"Spotify": '
        return ""


@pytest.fixture
def desks(monkeypatch, tmp_path: Path):
    apps = tmp_path / "Applications"
    (apps / "Spotify.app").mkdir(parents=True)
    monkeypatch.setattr(local_intents, "APP_FOLDERS", (apps,))
    kit, mac = FakeEventKit(), FakeMac()
    return kit, mac, AppleDesk(run=kit), MacDesk(run=mac, start=lambda argv: None)


def ask(text: str, desks):
    _, _, apple, mac = desks
    return answer(text, apple=apple, mac=mac, now=NOW)


def test_get_done_reads_adds_and_checks_off(desks) -> None:
    kit = desks[0]
    assert ask("what's on my list?", desks).reply.startswith("GET DONE (3):")
    assert ask("Add pick up dry cleaning to GET DONE", desks).reply == "Added to GET DONE: pick up dry cleaning."
    assert kit.items[-1]["title"] == "Pick up dry cleaning"
    assert ask("check off real id", desks).reply == "Checked off: Get a REAL ID."
    assert ask("check off request", desks) is None  # two items match: the model asks which


def test_calendar_today_tomorrow_and_next(desks) -> None:
    assert ask("what's on my calendar tomorrow", desks).reply.startswith("Tomorrow:\n- 1 PM ECON 412")
    assert "Tutoring" in ask("what do I have today?", desks).reply


def test_mac_requests_run_without_a_model(desks) -> None:
    mac = desks[1]
    assert ask("open spotify", desks).reply == "Opened Spotify."
    assert ["open", "-a", "Spotify"] in mac.calls
    assert ask("volume 30", desks).reply == "Volume 30."
    assert ask("pause the music", desks).reply == "Done."
    assert ask("lock my mac", desks).reply == "Locked."
    assert ask("keep my mac awake for 2 hours", desks).reply == "Keeping your Mac awake for 120 minutes."
    assert ask("run put the fan on auto", desks).reply == "Ran Put the fan on auto."


def test_anything_unclear_still_goes_to_the_model(desks) -> None:
    for text in (
        "open loops",  # not an installed app
        "run the tests",  # not one of his Shortcuts
        "mark day 19 posted",  # content, not GET DONE
        "remind me at 3 to call Sam",
        "how are you doing ARI",
        "what should I work on today?",
    ):
        assert ask(text, desks) is None, text


def test_nothing_changes_in_a_dry_run(desks) -> None:
    kit, mac, apple, mac_desk = desks
    assert answer("add milk to my list", apple=apple, mac=mac_desk, now=NOW, dry_run=True) is None
    assert answer("lock my mac", apple=apple, mac=mac_desk, now=NOW, dry_run=True) is None
    assert "add-reminder" not in kit.calls and mac.calls == []


def test_the_conversation_answers_plain_requests_without_calling_the_model(tmp_path: Path, desks) -> None:
    from ari_core.conversation import Conversation
    from ari_memory import create_engine, create_session_factory

    def no_model(**kwargs):
        raise AssertionError("the model was called")

    factory = create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))
    conversation = Conversation(channel="test", session_factory=factory, action_desk=None, respond=no_model,
                                apple=desks[2], mac=desks[3], now=lambda: NOW)
    turn = conversation.take("what's on my list", [])
    assert turn.reply.startswith("GET DONE (3):")
    assert turn.messages[-1]["content"][0]["text"] == turn.reply  # kept, so a follow-up has context
