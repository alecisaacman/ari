"""ARI's iMessage surface: one poll of the self-thread.

This is an ACE surface, not a brain. Each poll reads new messages from the
self-thread snapshot and hands each one to ARI's conversation
(`ari_core.conversation`), which decides what it means, the same as on every
surface, and sends the reply back into the thread.

Then ARI's signal engine runs on schedule, and ARI sends any new important
alerts, with the reason it raised them, and any reminders that are due.

The cursor and conversation are saved after every message, so a crash never
replays a message that already got a reply.
"""

from __future__ import annotations

import fcntl
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ari_core.action_desk import ActionDesk
from ari_core.brain import respond_to_message, roll_history
from ari_core.conversation import Conversation, Respond
from ari_core.core.pause import get_pause_state
from ari_core.memory import get_conversation_state, save_conversation_state
from ari_core.orchestration import RunSignalOrchestrationInput, run_signal_orchestration
from ari_core.reminders import due_reminders, mark_sent
from ari_memory.tables import AlertRow
from ari_state import AlertChannel, AlertEscalationLevel, AlertStatus
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .config import ImessageSettings
from .dump import DumpRow, DumpUnavailable, read_dump
from .messages_app import MessagesApp

CHANNEL = "imessage"
ECHO_WINDOW = 12
ALERT_LOOKBACK = timedelta(hours=24)
# A message answered this long after it was sent gets an honest explanation first.
LATE_AFTER = timedelta(minutes=3)
SENT_LOG_SIZE = 50
# ARI's signal engine is deterministic and free; it runs this often while ARI is awake.
ORCHESTRATE_EVERY = timedelta(minutes=30)
NOTIFY_LEVELS = {
    AlertEscalationLevel.ELEVATED.value,
    AlertEscalationLevel.INTERRUPTIVE.value,
    AlertEscalationLevel.URGENT.value,
}

@dataclass(slots=True)
class PollReport:
    status: str = "ok"
    detail: str = ""
    handled: int = 0
    replies: list[str] = field(default_factory=list)
    alerts_sent: int = 0
    signals_raised: int = 0
    reminders_sent: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "detail": self.detail,
            "handled": self.handled,
            "replies": self.replies,
            "alertsSent": self.alerts_sent,
            "signalsRaised": self.signals_raised,
            "remindersSent": self.reminders_sent,
        }


class ImessageGateway:
    def __init__(
        self,
        *,
        settings: ImessageSettings,
        session_factory: sessionmaker[Session],
        action_desk: ActionDesk | None,
        messages_app: MessagesApp | None = None,
        respond: Respond = respond_to_message,
        now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
        dry_run: bool = False,
        signal_engine: bool = True,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.action_desk = action_desk
        self.messages_app = messages_app or MessagesApp()
        self.respond = respond
        self.now = now
        self.dry_run = dry_run
        self.signal_engine = signal_engine
        self.conversation = Conversation(
            channel=CHANNEL,
            session_factory=session_factory,
            action_desk=action_desk,
            save_for_later=self._save_for_later,
            respond=respond,
            now=now,
            dry_run=dry_run,
        )

    def poll_once(self) -> PollReport:
        report = PollReport()
        if not self.settings.self_identifiers or not self.settings.reply_to:
            return PollReport(status="not_configured", detail="Set ARI_IMESSAGE_TO.")
        with self._exclusive() as acquired:
            if not acquired:
                return PollReport(status="busy", detail="Another poll is running.")
            try:
                rows = read_dump(self.settings.dump_path, stale_after=self.settings.stale_after)
            except DumpUnavailable as error:
                return PollReport(status="dump_unavailable", detail=str(error))
            # When ARI last ran, recorded before this run, explains any late reply.
            self._previous_run = self._read_heartbeat()
            self._late_notice_sent = False
            self._write_heartbeat()
            with self.session_factory() as session:
                state = get_conversation_state(session, channel=CHANNEL)
            if state is None:
                # First run: start from now instead of answering the whole thread.
                self._save(rows[-1].rowid if rows else 0, [])
                return PollReport(status="seeded", detail="Started from the latest message.")
            cursor, history = state.cursor, list(state.messages)
            for row in (row for row in rows if row.rowid > cursor):
                try:
                    history = self._handle(row, history, report)
                except Exception as error:  # noqa: BLE001 - stop here; retry this message next poll
                    report.status = "error"
                    report.detail = f"Message {row.rowid} failed: {type(error).__name__}: {error}"
                    return report
                cursor = row.rowid
                self._save(cursor, history)
            # A message may have changed ARI's state, so the engine re-checks before alerts go out.
            self._maybe_orchestrate(report, force=report.handled > 0)
            history = self._send_alerts(history, report)
            history = self._send_reminders(history, report)
            self._save(cursor, history)
        return report

    def _maybe_orchestrate(self, report: PollReport, *, force: bool = False) -> None:
        """Run ARI's signal engine on schedule, so ARI notices things without being asked."""
        if not self.signal_engine or self.dry_run or get_pause_state()["paused"]:
            return
        marker = self.settings.state_dir / "last-orchestration"
        now = self.now()
        try:
            last = datetime.fromisoformat(marker.read_text().strip())
        except (OSError, ValueError):
            last = None
        if not force and last is not None and now - last < ORCHESTRATE_EVERY:
            return
        marker.write_text(now.isoformat())
        try:
            with self.session_factory() as session:
                result = run_signal_orchestration(
                    session,
                    RunSignalOrchestrationInput(
                        state_date=now.astimezone().date(),
                        detected_at=now,
                        alert_channel=AlertChannel.PHONE,
                    ),
                )
            report.signals_raised = len(result.signals)
        except Exception as error:  # noqa: BLE001 - a failed run is reported, never fatal to messaging
            report.detail = f"Signal engine failed: {type(error).__name__}: {error}"

    def _handle(self, row: DumpRow, history: list[dict[str, Any]], report: PollReport) -> list[dict[str, Any]]:
        text = row.text
        if row.is_tapback or not text or _normalize(text) in _recent_replies(history) | self._sent_log():
            # Reactions are not messages, and in a self-thread ARI's own replies
            # come back looking like Alec's; they are recognized by their text.
            return history
        report.handled += 1
        # poll_once refuses to run without a reply handle.
        reply_to = row.chat_identifier or self.settings.reply_to or ""
        self._explain_if_late(row, reply_to, report)
        turn = self.conversation.take(text, history)
        if turn.reply:
            self._send(reply_to, turn.reply, report)
        return turn.messages

    def _send_alerts(self, history: list[dict[str, Any]], report: PollReport) -> list[dict[str, Any]]:
        if get_pause_state()["paused"]:
            return history
        now = self.now()
        with self.session_factory() as session:
            rows = session.scalars(
                select(AlertRow).where(
                    AlertRow.status == AlertStatus.PENDING.value,
                    AlertRow.sent_at.is_(None),
                    AlertRow.escalation_level.in_(NOTIFY_LEVELS),
                )
            ).all()
            for alert in sorted(rows, key=lambda row: _utc(row.created_at)):
                if now - _utc(alert.created_at) > ALERT_LOOKBACK:
                    continue
                if alert.escalation_level != AlertEscalationLevel.URGENT.value and self._quiet(now):
                    continue
                body = _phone_text(alert)
                if self._send(self.settings.reply_to or "", body, report) and not self.dry_run:
                    alert.sent_at = now
                    alert.status = AlertStatus.SENT.value
                    report.alerts_sent += 1
                    # Kept in the conversation so a reply like "why?" has context.
                    history = [*history, {"role": "assistant", "content": [{"type": "text", "text": body}]}] if history else history
            if not self.dry_run:
                session.commit()
        return history

    def _send_reminders(self, history: list[dict[str, Any]], report: PollReport) -> list[dict[str, Any]]:
        """Text Alec the reminders that are due. He chose the time, so quiet hours don't hold them."""
        if self.dry_run or get_pause_state()["paused"]:
            return history
        now = self.now()
        with self.session_factory() as session:
            for reminder in due_reminders(session, now=now):
                body = f"Reminder: {reminder.text}"
                if now - reminder.remind_at > LATE_AFTER:
                    body += f" (This was due at {_clock(reminder.remind_at)}; I wasn't running then.)"
                if not self._send(self.settings.reply_to or "", body, report):
                    break
                mark_sent(session, reminder.id, sent_at=now)
                report.reminders_sent += 1
                if history:
                    history = [*history, {"role": "assistant", "content": [{"type": "text", "text": body}]}]
        return history

    def _quiet(self, now: datetime) -> bool:
        if self.settings.quiet_hours is None:
            return False
        start, end = self.settings.quiet_hours
        hour = now.astimezone().hour
        if start > end:  # wraps past midnight, e.g. 22-7
            return hour >= start or hour < end
        return start <= hour < end

    def _explain_if_late(self, row: DumpRow, handle: str, report: PollReport) -> None:
        """Say plainly why a reply is late, from facts ARI recorded, before answering."""
        now = self.now()
        if self._late_notice_sent or row.sent_at is None or now - row.sent_at < LATE_AFTER:
            return
        self._late_notice_sent = True
        sent = _clock(row.sent_at)
        previous = getattr(self, "_previous_run", None)
        if previous is not None and now - previous >= LATE_AFTER:
            notice = (
                f"Sorry for the slow reply. You sent this at {sent}, and I couldn't see it until now: "
                f"I wasn't running from {_clock(previous)} to {_clock(now)}, most likely because your Mac was asleep."
            )
        else:
            notice = f"Sorry for the slow reply. You sent this at {sent}, and I'm only answering it now."
        self._send(handle, notice, report)

    def _read_heartbeat(self) -> datetime | None:
        try:
            return datetime.fromisoformat((self.settings.state_dir / "last-run").read_text().strip())
        except (OSError, ValueError):
            return None

    def _write_heartbeat(self) -> None:
        if self.dry_run:
            return
        self.settings.state_dir.mkdir(parents=True, exist_ok=True)
        (self.settings.state_dir / "last-run").write_text(self.now().isoformat())

    def _sent_log(self) -> set[str]:
        """Everything ARI sent recently, so its own messages are never answered, whatever produced them."""
        try:
            return set(json.loads((self.settings.state_dir / "sent.json").read_text()))
        except (OSError, ValueError):
            return set()

    def _record_sent(self, body: str) -> None:
        path = self.settings.state_dir / "sent.json"
        try:
            sent = json.loads(path.read_text())
        except (OSError, ValueError):
            sent = []
        path.write_text(json.dumps([*sent, _normalize(body)][-SENT_LOG_SIZE:]))

    def _send(self, handle: str, body: str, report: PollReport) -> bool:
        report.replies.append(body)
        if self.dry_run:
            return True
        # Recorded before sending: the echo can come back before the send call returns.
        self._record_sent(body)
        sent = self.messages_app.send(handle, body)
        if not sent:
            # Usually the macOS Automation permission for Messages; surfaced in the log.
            report.status = "send_failed"
            report.detail = f"Messages did not send: {self.messages_app.last_error or 'no error text'}"
        return sent

    def _save(self, cursor: int, history: list[dict[str, Any]]) -> None:
        if self.dry_run:
            return
        with self.session_factory() as session:
            save_conversation_state(session, channel=CHANNEL, cursor=cursor, messages=roll_history(history))

    def _save_for_later(self, link: str, note: str | None) -> None:
        saved = self.settings.state_dir / "watch-later.md"
        saved.parent.mkdir(parents=True, exist_ok=True)
        suffix = f" - {note}" if note else ""
        with saved.open("a", encoding="utf-8") as handle:
            handle.write(f"- [{self.now().isoformat()}] {link}{suffix}\n")

    @contextmanager
    def _exclusive(self) -> Iterator[bool]:
        self.settings.state_dir.mkdir(parents=True, exist_ok=True)
        with (self.settings.state_dir / "poll.lock").open("w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            yield True


def _recent_replies(history: list[dict[str, Any]]) -> set[str]:
    texts: list[str] = []
    for message in reversed(history):
        content = message.get("content")
        if message.get("role") != "assistant" or not isinstance(content, list):
            continue
        blocks = [
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        # A reply is sent as all of a turn's text blocks joined, so match both.
        texts.extend([_normalize(text) for text in blocks] + [_normalize("".join(blocks))])
        if len(texts) >= ECHO_WINDOW:
            break
    return {text for text in texts if text}


def _normalize(text: str) -> str:
    """Compare messages as Messages may store them: whitespace runs and quote styles differ."""
    for curly, straight in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"')):
        text = text.replace(curly, straight)
    return " ".join(text.split())


# How ARI says an alert in a text. The engine's wording stays in ARI's records for
# explanation; a reply like "why?" lets the brain read it.
PHONE_TEXT = {
    "No daily check-in recorded": "You haven't checked in today. What are your priorities, and what would make today a win?",
}


def _phone_text(alert: AlertRow) -> str:
    return PHONE_TEXT.get(alert.title) or f"{alert.title}. {alert.message or alert.reason}".strip()


def _clock(moment: datetime) -> str:
    return moment.astimezone().strftime("%-I:%M %p")


def _utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; ARI stores UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)
