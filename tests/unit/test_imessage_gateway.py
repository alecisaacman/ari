from __future__ import annotations

import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from ari_core.action_desk import ActionDesk
from ari_core.brain import BrainResponse
from ari_core.core import pause as pause_module
from ari_imessage_gateway.config import ImessageSettings
from ari_imessage_gateway.gateway import ImessageGateway
from ari_imessage_gateway.launchd import dump_query, render_plists
from ari_imessage_gateway.messages_app import MessagesApp
from ari_memory import create_engine, create_session_factory
from ari_memory.tables import AlertRow
from sqlalchemy.orm import Session, sessionmaker

SELF = "+15555550100"


class FakeMessages(MessagesApp):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[tuple[str, str]] = []

    def send(self, handle: str, body: str) -> bool:
        self.sent.append((handle, body))
        return True


class FakeBrain:
    """Stands in for ARI's brain; records what reached it and can call tools."""

    def __init__(self, reply: str = "On it.", tool_call: tuple[str, dict[str, Any]] | None = None) -> None:
        self.reply = reply
        self.tool_call = tool_call
        self.texts: list[str] = []
        self.tool_results: list[dict[str, Any]] = []

    def __call__(self, *, text, history, dispatch_tool, **_: Any) -> BrainResponse:
        self.texts.append(text)
        if self.tool_call is not None:
            self.tool_results.append(dispatch_tool(*self.tool_call))
        messages = [
            *history,
            {"role": "user", "content": text},
            {"role": "assistant", "content": [{"type": "text", "text": self.reply}]},
        ]
        return BrainResponse(reply=self.reply, messages=messages)


@pytest.fixture
def ledger_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("ari-state")


@pytest.fixture
def session_factory(ledger_dir: Path) -> sessionmaker[Session]:
    return create_session_factory(create_engine(f"sqlite+pysqlite:///{ledger_dir / 'ari.db'}"))


@pytest.fixture(autouse=True)
def isolated_pause(monkeypatch: pytest.MonkeyPatch, ledger_dir: Path) -> None:
    monkeypatch.setattr(pause_module, "PAUSED_MARKER_PATH", ledger_dir / ".paused")


@pytest.fixture
def settings(ledger_dir: Path) -> ImessageSettings:
    state_dir = ledger_dir / "imessage"
    state_dir.mkdir()
    return ImessageSettings(
        self_identifiers=(SELF,),
        reply_to=SELF,
        dump_path=state_dir / "self-thread.tsv",
        state_dir=state_dir,
        quiet_hours=None,
    )


def write_dump(settings: ImessageSettings, *rows: tuple[int, str] | tuple[int, str, int]) -> None:
    lines = []
    for row in rows:
        rowid, text = row[0], row[1]
        associated = row[2] if len(row) > 2 else 0
        lines.append(f"{rowid}|{text.encode().hex()}||0|{SELF}|{associated}")
    settings.dump_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_gateway(settings, session_factory, *, brain=None, desk=None, messages=None, **kwargs) -> ImessageGateway:
    return ImessageGateway(
        settings=settings,
        session_factory=session_factory,
        action_desk=desk,
        messages_app=messages or FakeMessages(),
        respond=brain or FakeBrain(),
        **kwargs,
    )


def seed(gateway: ImessageGateway, settings: ImessageSettings, last_rowid: int = 1) -> None:
    write_dump(settings, (last_rowid, "old message"))
    assert gateway.poll_once().status == "seeded"


def test_first_poll_starts_from_now_instead_of_replaying_the_thread(settings, session_factory) -> None:
    brain = FakeBrain()
    gateway = make_gateway(settings, session_factory, brain=brain)
    write_dump(settings, (1, "very old"), (2, "also old"))

    assert gateway.poll_once().status == "seeded"
    assert gateway.poll_once().handled == 0
    assert brain.texts == []


def test_new_message_reaches_the_brain_and_the_reply_is_sent(settings, session_factory) -> None:
    brain = FakeBrain(reply="You have two open loops.")
    messages = FakeMessages()
    gateway = make_gateway(settings, session_factory, brain=brain, messages=messages)
    seed(gateway, settings)
    write_dump(settings, (1, "old message"), (2, "What's on my plate?"))

    report = gateway.poll_once()

    assert report.handled == 1
    assert brain.texts == ["What's on my plate?"]
    assert messages.sent == [(SELF, "You have two open loops.")]


def test_own_replies_and_tapbacks_are_not_treated_as_new_messages(settings, session_factory) -> None:
    brain = FakeBrain(reply="Filed it.")
    gateway = make_gateway(settings, session_factory, brain=brain)
    seed(gateway, settings)
    write_dump(settings, (1, "old message"), (2, "Remind me to call Sam"))
    gateway.poll_once()
    # ARI's reply lands in the self-thread as if Alec sent it, plus a tapback.
    write_dump(settings, (1, "old message"), (2, "Remind me to call Sam"), (3, "Filed it."), (4, "Loved it", 2000))

    assert gateway.poll_once().handled == 0
    assert brain.texts == ["Remind me to call Sam"]


def test_a_message_that_fails_is_retried_without_replaying_earlier_ones(settings, session_factory) -> None:
    calls: list[str] = []

    def flaky(*, text, history, **_: Any) -> BrainResponse:
        calls.append(text)
        if text == "second" and calls.count("second") == 1:
            raise RuntimeError("model unavailable")
        return BrainResponse(reply=f"ok {text}", messages=[*history, {"role": "user", "content": text}])

    messages = FakeMessages()
    gateway = make_gateway(settings, session_factory, brain=flaky, messages=messages)
    seed(gateway, settings)
    write_dump(settings, (1, "old message"), (2, "first"), (3, "second"))

    assert gateway.poll_once().status == "error"
    assert gateway.poll_once().status == "ok"
    assert calls == ["first", "second", "second"]
    assert [body for _, body in messages.sent] == ["ok first", "ok second"]


def test_stop_pauses_ari_and_nothing_else_is_acted_on_until_resume(settings, session_factory) -> None:
    brain = FakeBrain()
    messages = FakeMessages()
    gateway = make_gateway(settings, session_factory, brain=brain, messages=messages)
    seed(gateway, settings)
    write_dump(settings, (1, "old message"), (2, "ARI stop"), (3, "draft my cover letter"))

    gateway.poll_once()

    assert pause_module.get_pause_state()["paused"] is True
    assert brain.texts == []
    write_dump(settings, (1, "old"), (2, "ARI stop"), (3, "draft my cover letter"), (4, "ARI resume"), (5, "hi"))
    gateway.poll_once()
    assert pause_module.get_pause_state()["paused"] is False
    assert brain.texts == ["hi"]
    assert "Paused" in messages.sent[0][1]
    assert "Resumed" in messages.sent[1][1]


def test_proposal_waits_for_alec_and_yes_runs_it_once_through_the_gateway(
    settings, session_factory, ledger_dir: Path, tmp_path: Path
) -> None:
    desk = ActionDesk(ledger_dir / "ledger.db", pause_state_reader=lambda: {"paused": False})
    brain = FakeBrain(
        reply="I can add that note. Reply yes to approve.",
        tool_call=(
            "propose_action",
            {
                "action_type": "write_file",
                "path": "notes/today.md",
                "content": "Call Sam Thursday\n",
                "summary": "Write notes/today.md with the reminder to call Sam.",
            },
        ),
    )
    messages = FakeMessages()
    gateway = make_gateway(settings, session_factory, brain=brain, desk=desk, messages=messages)
    seed(gateway, settings)
    write_dump(settings, (1, "old"), (2, "Add 'call Sam Thursday' to today's notes"))

    gateway.poll_once()

    assert "proposal_id" in brain.tool_results[0]
    assert not (tmp_path / "notes" / "today.md").exists()
    assert [item.summary for item in desk.pending()] == ["Write notes/today.md with the reminder to call Sam."]

    write_dump(settings, (1, "old"), (2, "Add 'call Sam Thursday' to today's notes"), (3, "Yes"))
    gateway.poll_once()

    assert (tmp_path / "notes" / "today.md").read_text(encoding="utf-8") == "Call Sam Thursday\n"
    assert desk.pending() == []
    assert messages.sent[-1][1].startswith("Done.")
    # "Yes" was decided by ARI from Alec's reply; it never reached the model.
    assert brain.texts == ["Add 'call Sam Thursday' to today's notes"]


def test_no_cancels_the_proposal(settings, session_factory, ledger_dir: Path, tmp_path: Path) -> None:
    desk = ActionDesk(ledger_dir / "ledger.db", pause_state_reader=lambda: {"paused": False})
    desk.propose(
        {"action_type": "write_file", "path": "x.txt", "content": "x", "summary": "Write x.txt."},
        surface="imessage",
    )
    messages = FakeMessages()
    gateway = make_gateway(settings, session_factory, desk=desk, messages=messages)
    seed(gateway, settings)
    write_dump(settings, (1, "old"), (2, "no"))

    gateway.poll_once()

    assert desk.pending() == []
    assert not (tmp_path / "x.txt").exists()
    assert messages.sent[-1][1] == "Cancelled: Write x.txt."


def test_yes_with_several_proposals_asks_which_one(settings, session_factory, ledger_dir: Path) -> None:
    desk = ActionDesk(ledger_dir / "ledger.db", pause_state_reader=lambda: {"paused": False})
    for name in ("a", "b"):
        desk.propose(
            {"action_type": "write_file", "path": f"{name}.txt", "content": name, "summary": f"Write {name}.txt."},
            surface="imessage",
        )
    messages = FakeMessages()
    gateway = make_gateway(settings, session_factory, desk=desk, messages=messages)
    seed(gateway, settings)
    write_dump(settings, (1, "old"), (2, "yes"))

    gateway.poll_once()

    assert "2 things are waiting" in messages.sent[-1][1]
    assert len(desk.pending()) == 2


def test_proposal_outside_the_workspace_is_refused(ledger_dir: Path) -> None:
    desk = ActionDesk(ledger_dir / "ledger.db", pause_state_reader=lambda: {"paused": False})

    result = desk.propose(
        {"action_type": "write_file", "path": "../escape.txt", "content": "x", "summary": "Escape."},
        surface="imessage",
    )

    assert "error" in result
    assert desk.pending() == []


def test_approval_survives_an_expired_lease(ledger_dir: Path, tmp_path: Path) -> None:
    clock = {"now": datetime(2026, 10, 20, 9, 0, tzinfo=UTC)}
    desk = ActionDesk(
        ledger_dir / "ledger.db",
        clock=lambda: clock["now"],
        pause_state_reader=lambda: {"paused": False},
    )
    desk.propose(
        {"action_type": "write_file", "path": "late.txt", "content": "late\n", "summary": "Write late.txt."},
        surface="imessage",
    )
    # Alec answers the next day, long after the worker's lease expired.
    clock["now"] += timedelta(days=1)

    step = desk.approve(desk.pending()[0].task_id, approved_by="alec", reason="test")

    assert step.succeeded
    assert (tmp_path / "late.txt").read_text(encoding="utf-8") == "late\n"


def test_important_alerts_are_sent_once_with_their_reason(settings, session_factory) -> None:
    now = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
    with session_factory() as session:
        for level, title in (("elevated", "Application deadline"), ("visible", "Minor note")):
            session.add(
                AlertRow(
                    id=uuid4(),
                    state_date=date(2026, 10, 20),
                    fingerprint=title,
                    status="pending",
                    channel="phone",
                    escalation_level=level,
                    title=title,
                    message="",
                    reason="The Stripe application closes tomorrow and is still a draft",
                    source_signal_ids=[],
                    created_at=now - timedelta(hours=1),
                )
            )
        session.commit()
    messages = FakeMessages()
    gateway = make_gateway(settings, session_factory, messages=messages, now=lambda: now)
    seed(gateway, settings)

    assert gateway.poll_once().alerts_sent == 1
    assert gateway.poll_once().alerts_sent == 0
    assert messages.sent == [
        (SELF, "Application deadline. The Stripe application closes tomorrow and is still a draft")
    ]


def test_dry_run_sends_and_saves_nothing(settings, session_factory) -> None:
    gateway = make_gateway(settings, session_factory)
    seed(gateway, settings)
    messages = FakeMessages()
    dry = make_gateway(settings, session_factory, messages=messages, dry_run=True)
    write_dump(settings, (1, "old"), (2, "hello"))

    report = dry.poll_once()

    assert report.replies == ["On it."]
    assert messages.sent == []
    assert make_gateway(settings, session_factory).poll_once().handled == 1


def test_stale_dump_is_reported_not_guessed(settings, session_factory) -> None:
    write_dump(settings, (1, "x"))
    old = (datetime.now() - timedelta(minutes=10)).timestamp()
    import os

    os.utime(settings.dump_path, (old, old))

    assert make_gateway(settings, session_factory).poll_once().status == "dump_unavailable"


def test_messages_app_passes_text_as_arguments_not_script() -> None:
    calls: list[list[str]] = []

    def runner(argv, **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    MessagesApp(runner=runner).send(SELF, 'say "hi" & do shell script "rm -rf ~"')

    assert calls[0][-2:] == [SELF, 'say "hi" & do shell script "rm -rf ~"']
    assert "rm -rf" not in calls[0][2]


def test_dump_job_runs_sqlite3_directly_and_escapes_identifiers(settings) -> None:
    query = dump_query(("+15555550100", "o'brien@icloud.com"))
    plists = render_plists(settings, label_prefix="com.test.ari", source_root=Path("/src"))

    assert "'o''brien@icloud.com'" in query
    import plistlib

    dump = plistlib.loads(plists["com.test.ari.imessage-dump.plist"])
    assert dump["ProgramArguments"][0] == "/usr/bin/sqlite3"
    assert "-readonly" in dump["ProgramArguments"]
    poll = plistlib.loads(plists["com.test.ari.imessage-poll.plist"])
    assert "ANTHROPIC_API_KEY" not in poll.get("EnvironmentVariables", {})
