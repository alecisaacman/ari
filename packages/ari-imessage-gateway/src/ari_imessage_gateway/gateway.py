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
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ari_core.action_desk import ActionDesk
from ari_core.apple import AppleDesk, AppleError
from ari_core.brain import respond_to_message, roll_history
from ari_core.build_story import Write as StoryWriter
from ari_core.build_story import building_days, run_story, story_repo
from ari_core.builder import announcement, unannounced
from ari_core.conversation import Conversation, Respond
from ari_core.core.pause import get_pause_state
from ari_core.get_done_watch import describe as describe_get_done
from ari_core.get_done_watch import mark_seen, new_from_alec
from ari_core.email_reader import EmailDesk
from ari_core.mac import MacDesk
from ari_core.memory import get_conversation_state, save_conversation_state
from ari_core.orchestration import RunSignalOrchestrationInput, run_signal_orchestration
from ari_core.pet_status import build_pet_status, note_credits, write_pet_status
from ari_core.reminders import due_reminders, mark_sent
from ari_core.self_review import Write as ReviewWriter
from ari_core.self_review import run_review
from ari_core.watchdog import RECORDS, Problem, Watchdog, check_records
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
# A day's build story goes out at night, after the night review.
STORY_FROM = (21, 30)
STORY_UNTIL = (23, 59)
# How Anthropic says ARI can't spend: no credits left, or Alec's monthly spend limit reached.
CREDITS_GONE = ("credit balance is too low", "reached your specified api usage limits")
# How long a poll waits for a fresh dump it asked for.
DUMP_REFRESH_WAIT_SECONDS = 5.0
# GET DONE is read through the EventKit helper, so ARI looks once a minute, not every poll.
GET_DONE_LOOK_EVERY = timedelta(minutes=1)
# How long a failure lasts before the watchdog texts Alec, so blips that clear themselves stay quiet.
MESSAGE_FAILING_AFTER = timedelta(minutes=10)
GET_DONE_FAILING_AFTER = timedelta(minutes=30)
SIGNAL_ENGINE_FAILING_AFTER = timedelta(hours=1)
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
    reviews_sent: int = 0
    get_done_noticed: int = 0
    builds_announced: int = 0
    stories_sent: int = 0
    watchdog_sent: int = 0
    # What failed this poll, and what ran and worked, for ARI's watchdog.
    problems: list[Problem] = field(default_factory=list)
    cleared: set[str] = field(default_factory=set)

    def problem(self, problem: Problem) -> None:
        """Record a failure: in the log line, and for the watchdog to text Alec."""
        self.problems.append(problem)
        self.detail = problem.text

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "detail": self.detail,
            "handled": self.handled,
            "replies": self.replies,
            "alertsSent": self.alerts_sent,
            "signalsRaised": self.signals_raised,
            "remindersSent": self.reminders_sent,
            "reviewsSent": self.reviews_sent,
            "getDoneNoticed": self.get_done_noticed,
            "buildsAnnounced": self.builds_announced,
            "storiesSent": self.stories_sent,
            "watchdogSent": self.watchdog_sent,
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
        apple: AppleDesk | None = None,
        review_writer: ReviewWriter | None = None,
        pet_status_path: Path | None = None,
        refresh_dump: Callable[[], None] | None = None,
        mac: MacDesk | None = None,
        mail: EmailDesk | None = None,
        story_writer: StoryWriter | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.action_desk = action_desk
        self.messages_app = messages_app or MessagesApp()
        self.respond = respond
        self.now = now
        self.dry_run = dry_run
        self.signal_engine = signal_engine
        self.apple = apple
        # Morning and night reviews call a model; without a writer they are off.
        self.review_writer = review_writer
        # Where the desktop pet reads ARI's status; None leaves it alone (tests).
        self.pet_status_path = pet_status_path
        # Asks launchd to run the dump job now; used when the snapshot is stale.
        self.refresh_dump = refresh_dump
        self.story_writer = story_writer
        self.conversation = Conversation(
            channel=CHANNEL,
            session_factory=session_factory,
            action_desk=action_desk,
            save_for_later=self._save_for_later,
            respond=respond,
            now=now,
            dry_run=dry_run,
            apple=apple,
            review_writer=review_writer,
            mac=mac,
            mail=mail,
            story_writer=story_writer,
        )

    def poll_once(self) -> PollReport:
        report = PollReport()
        if not self.settings.self_identifiers or not self.settings.reply_to:
            return PollReport(status="not_configured", detail="Set ARI_IMESSAGE_TO.")
        with self._exclusive() as acquired:
            if not acquired:
                return PollReport(status="busy", detail="Another poll is running.")
            try:
                rows = self._read_dump()
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
            if any(row.rowid > cursor for row in rows):
                self._update_pet(thinking=True)
            # What piled up while ARI couldn't run, for the gap notice.
            self._waiting = sum(1 for row in rows if row.rowid > cursor and row.text and not row.is_tapback)
            for row in (row for row in rows if row.rowid > cursor):
                try:
                    history = self._handle(row, history, report)
                except Exception as error:  # noqa: BLE001 - stop here; retry this message next poll
                    report.status = "error"
                    report.problem(Problem(
                        key=f"message-{row.rowid}",
                        text=(f"A message you sent keeps failing ({type(error).__name__}: {error}). "
                              "I'm retrying it, and the ones after it wait until it goes through."),
                        label="Answering your messages",
                        after=MESSAGE_FAILING_AFTER,
                    ))
                    self._watch(history, report)
                    return report
                report.cleared.add(f"message-{row.rowid}")
                cursor = row.rowid
                self._save(cursor, history)
            # A message may have changed ARI's state, so the engine re-checks before alerts go out.
            self._maybe_orchestrate(report, force=report.handled > 0)
            history = self._send_alerts(history, report)
            history = self._send_reminders(history, report)
            history = self._send_reviews(history, report)
            history = self._notice_get_done(history, report)
            history = self._announce_builds(history, report)
            history = self._send_story(history, report)
            history = self._watch(history, report)
            self._save(cursor, history)
            self._update_pet(thinking=False)
        return report

    def _read_dump(self) -> list[DumpRow]:
        """The snapshot, refreshed first if it's stale.

        After the Mac wakes, launchd can run the poll before the dump catches up. ARI asks
        for a fresh dump and waits a moment, instead of skipping this poll.
        """
        try:
            return read_dump(self.settings.dump_path, stale_after=self.settings.stale_after)
        except DumpUnavailable:
            if self.refresh_dump is None:
                raise
        self.refresh_dump()
        deadline = time.monotonic() + DUMP_REFRESH_WAIT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(0.25)
            try:
                return read_dump(self.settings.dump_path, stale_after=self.settings.stale_after)
            except DumpUnavailable:
                continue
        return read_dump(self.settings.dump_path, stale_after=self.settings.stale_after)

    def _update_pet(self, *, thinking: bool) -> None:
        """Keep the desktop pet's status file current. A failure here never stops messaging."""
        if self.dry_run or self.pet_status_path is None:
            return
        try:
            waiting = len(self.action_desk.pending()) if self.action_desk else 0
            with self.session_factory() as session:
                status = build_pet_status(
                    session, now=self.now(), thinking=thinking, waiting_for_approval=waiting
                )
            write_pet_status(status, self.pet_status_path)
        except Exception:  # noqa: BLE001
            pass

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
            report.cleared.add("signal-engine")
        except Exception as error:  # noqa: BLE001 - a failed run is reported, never fatal to messaging
            report.problem(Problem(
                key="signal-engine",
                text=(f"My signal engine keeps failing ({type(error).__name__}: {error}), so I'm not "
                      "noticing things on my own until it's fixed."),
                label="My signal engine",
                after=SIGNAL_ENGINE_FAILING_AFTER,
            ))

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

    def _send_reviews(self, history: list[dict[str, Any]], report: PollReport) -> list[dict[str, Any]]:
        """Send the morning or night review once a day, at the time Alec set or when ARI next runs."""
        if self.review_writer is None or self.dry_run or get_pause_state()["paused"]:
            return history
        local = self.now().astimezone()
        for kind, at in self.settings.review_times.items():
            if at is None or not _review_due(kind, at, local):
                continue
            marker = self.settings.state_dir / f"last-review-{kind}"
            try:
                if marker.read_text().strip() == local.date().isoformat():
                    continue
            except OSError:
                pass
            marker.write_text(local.date().isoformat())  # once a day, even if writing fails
            with self.session_factory() as session:
                reasons: list[str] = []
                review = run_review(
                    session, kind=kind, now=self.now(), apple=self.apple, write=self.review_writer,
                    on_skip=reasons.append,
                )
            if review is None:
                why = f": {reasons[0]}" if reasons else ""
                text = f"The {kind} review didn't get written{why}."
                if reasons and any(phrase in reasons[0].lower() for phrase in CREDITS_GONE):
                    # The credits notice already tells Alec, once a day.
                    report.detail = text
                    history = self._say_out_of_credits(history, report, local)
                else:
                    report.problem(Problem(key=f"review-{kind}-{local.date().isoformat()}", text=text, lasting=False))
                continue
            if not self._send(self.settings.reply_to or "", review.message, report):
                continue
            report.reviews_sent += 1
            if history:
                history = [*history, {"role": "assistant", "content": [{"type": "text", "text": review.message}]}]
        return history

    def _say_out_of_credits(self, history: list[dict[str, Any]], report: PollReport, local: datetime) -> list[dict[str, Any]]:
        """Tell Alec once a day that the API credits are gone, since reviews and builds stop with them."""
        if self.pet_status_path is not None:
            note_credits(out=True)
        if self._told_credits_today(local):
            return history
        (self.settings.state_dir / "last-credits-notice").write_text(local.date().isoformat())
        body = (
            "Heads up: ARI can't use its Anthropic API right now (credits used up, or this month's spend "
            "limit reached), so I can't write reviews, answer you, or propose builds until that's sorted "
            "at console.anthropic.com. Nothing is lost."
        )
        if not self._send(self.settings.reply_to or "", body, report):
            return history
        return [*history, {"role": "assistant", "content": [{"type": "text", "text": body}]}] if history else history

    def _told_credits_today(self, local: datetime) -> bool:
        try:
            return (self.settings.state_dir / "last-credits-notice").read_text().strip() == local.date().isoformat()
        except OSError:
            return False

    def _send_reminders(self, history: list[dict[str, Any]], report: PollReport) -> list[dict[str, Any]]:
        """Text Alec the reminders that are due. He chose the time, so quiet hours don't hold them."""
        if self.dry_run or get_pause_state()["paused"]:
            return history
        now = self.now()
        with self.session_factory() as session:
            for reminder in due_reminders(session, now=now):
                if reminder.apple_id:
                    # Apple Reminders delivered this one on his phone; a text would repeat it.
                    mark_sent(session, reminder.id, sent_at=now)
                    continue
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

    def _notice_get_done(self, history: list[dict[str, Any]], report: PollReport) -> list[dict[str, Any]]:
        """Ask about what Alec added to GET DONE himself, e.g. offline or while the Mac slept.

        Quiet hours hold the question, and the items stay unseen until ARI can ask.
        """
        now = self.now()
        if self.apple is None or self.dry_run or get_pause_state()["paused"] or self._quiet(now):
            return history
        marker = self.settings.state_dir / "last-get-done-look"
        try:
            last = datetime.fromisoformat(marker.read_text().strip())
        except (OSError, ValueError):
            last = None
        if last is not None and now - last < GET_DONE_LOOK_EVERY:
            return history
        marker.write_text(now.isoformat())
        seen_path = self.settings.state_dir / "get-done-seen.json"
        try:
            items, ids = new_from_alec(self.apple, seen_path)
        except AppleError as error:
            report.problem(Problem(
                key="get-done",
                text=f"I haven't been able to read GET DONE for a while: {error}",
                label="Reading GET DONE",
                after=GET_DONE_FAILING_AFTER,
            ))
            return history
        report.cleared.add("get-done")
        if not items:
            mark_seen(seen_path, ids)
            return history
        body = describe_get_done(items)
        if not self._send(self.settings.reply_to or "", body, report):
            return history  # still unseen, so ARI asks again next look
        mark_seen(seen_path, ids)
        report.get_done_noticed += len(items)
        # Kept in the conversation so "yes" or "do the second one" has context.
        return [*history, {"role": "assistant", "content": [{"type": "text", "text": body}]}] if history else history

    def _announce_builds(self, history: list[dict[str, Any]], report: PollReport) -> list[dict[str, Any]]:
        """Tell Alec once when ARI's builder finishes, gets stuck on, or ships a build."""
        if self.dry_run or get_pause_state()["paused"] or self._quiet(self.now()):
            return history
        with self.session_factory() as session:
            for row in unannounced(session):
                body = announcement(row)
                if not self._send(self.settings.reply_to or "", body, report):
                    break
                row.announced_status = row.status
                session.commit()
                report.builds_announced += 1
                if history:
                    history = [*history, {"role": "assistant", "content": [{"type": "text", "text": body}]}]
        return history

    def _send_story(self, history: list[dict[str, Any]], report: PollReport) -> list[dict[str, Any]]:
        """Each night, on a day ARI was worked on, send that day's build story once."""
        repo = story_repo()
        if self.story_writer is None or self.dry_run or repo is None or get_pause_state()["paused"]:
            return history
        local = self.now().astimezone()
        if not STORY_FROM <= (local.hour, local.minute) <= STORY_UNTIL:
            return history
        marker = self.settings.state_dir / "last-story"
        try:
            if marker.read_text().strip() == local.date().isoformat():
                return history
        except OSError:
            pass
        marker.write_text(local.date().isoformat())  # once a night, even if writing fails
        if local.date() not in building_days(repo):
            return history  # nothing was built today, so there's no day to tell
        with self.session_factory() as session:
            story = run_story(session, repo=repo, day=local.date(), now=self.now(), write=self.story_writer)
        if story is None:
            text = "Today's build story didn't get written."
            if self._told_credits_today(local):
                report.detail = text  # the credits notice already explains it
            else:
                report.problem(Problem(key=f"story-{local.date().isoformat()}", text=text, lasting=False))
            return history
        body = story.message()
        if not self._send(self.settings.reply_to or "", body, report):
            return history
        report.stories_sent += 1
        return [*history, {"role": "assistant", "content": [{"type": "text", "text": body}]}] if history else history

    def _watch(self, history: list[dict[str, Any]], report: PollReport) -> list[dict[str, Any]]:
        """Text Alec what's failing, once, and when it works again. Quiet hours and a pause hold it."""
        if self.dry_run:
            return history
        now = self.now()
        watchdog = Watchdog(self.settings.state_dir / "watchdog.json")
        try:
            with self.session_factory() as session:
                records = check_records(session, now=now, builder_on=os.environ.get("ARI_AUTOBUILD") == "1")
            notices = watchdog.observe([*report.problems, *records], cleared={*report.cleared, RECORDS}, now=now)
        except Exception as error:  # noqa: BLE001 - the watchdog never stops messaging
            report.detail = f"The watchdog failed: {type(error).__name__}: {error}"
            return history
        if not notices or get_pause_state()["paused"] or self._quiet(now):
            return history
        for notice in notices:
            if not self._send(self.settings.reply_to or "", notice.body, report):
                break  # still waiting in the watchdog's file, for the next poll
            watchdog.told(notice)
            report.watchdog_sent += 1
            if history:
                history = [*history, {"role": "assistant", "content": [{"type": "text", "text": notice.body}]}]
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
            catch_up = self._catch_up()
            if catch_up:
                notice += f" {catch_up}"
        else:
            notice = f"Sorry for the slow reply. You sent this at {sent}, and I'm only answering it now."
        self._send(handle, notice, report)

    def _catch_up(self) -> str:
        """What ARI is doing about the gap, counted from its records: messages waiting, reminders missed."""
        waiting = getattr(self, "_waiting", 0)
        try:
            with self.session_factory() as session:
                missed = sum(1 for reminder in due_reminders(session, now=self.now()) if not reminder.apple_id)
        except Exception:  # noqa: BLE001 - the notice still goes out without the count
            missed = 0
        parts = []
        if waiting > 1:
            parts.append(f"answering your {waiting} messages in order")
        if missed:
            parts.append(f"sending {_count(missed, 'reminder')} that came due while I was off")
        return f"Catching up now: {' and '.join(parts)}." if parts else ""

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


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _clock(moment: datetime) -> str:
    return moment.astimezone().strftime("%-I:%M %p")


def _utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; ARI stores UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# A review that was missed while the Mac slept still goes out, until it would be stale.
REVIEW_DEADLINES = {"morning": (12, 0), "night": (23, 59)}


def _review_due(kind: str, at: tuple[int, int], local: datetime) -> bool:
    now = (local.hour, local.minute)
    return at <= now <= REVIEW_DEADLINES.get(kind, (23, 59))
