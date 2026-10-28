"""ARI's iMessage surface: one poll of the self-thread.

This is an ACE surface, not a brain. Each poll reads new messages from the
self-thread snapshot and, for each one, in order:

1. control commands ("ARI stop", "ARI resume") pause or resume ARI;
2. while paused, nothing else is acted on;
3. "ARI spend" and "ARI budget N" report or set the monthly model budget;
4. a "yes" or "no" with a proposal waiting approves or declines it. That is
   decided here, from Alec's own words, never by the model;
5. anything else goes to ARI's brain, unless this month's budget is used up,
   and its reply goes back into the thread.

Then ARI sends any new important alerts, with the reason it raised them.

The cursor and conversation are saved after every message, so a crash never
replays a message that already got a reply.
"""

from __future__ import annotations

import fcntl
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ari_core.action_desk import ActionDesk, PendingProposal, describe_result
from ari_core.brain import BrainResponse, make_tool_dispatcher, respond_to_message, roll_history
from ari_core.brain_usage import (
    ModelCall,
    month_spend,
    record_model_call,
    requests_since,
    set_monthly_budget_usd,
)
from ari_core.core.pause import get_pause_state, pause, resume
from ari_core.memory import get_conversation_state, save_conversation_state
from ari_core.skills import build_mcp_request_args, record_skill_invocation
from ari_memory.tables import AlertRow
from ari_state import AlertEscalationLevel, AlertStatus
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .config import ImessageSettings
from .dump import DumpRow, DumpUnavailable, read_dump
from .messages_app import MessagesApp

CHANNEL = "imessage"
SURFACE = "imessage"
ECHO_WINDOW = 12
ALERT_LOOKBACK = timedelta(hours=24)
# Circuit breaker: a burst of model requests this large is a loop, not Alec typing.
# Each message takes one to four requests, so this allows a fast exchange.
LOOP_WINDOW = timedelta(minutes=10)
LOOP_MAX_REQUESTS = 30
NOTIFY_LEVELS = {
    AlertEscalationLevel.ELEVATED.value,
    AlertEscalationLevel.INTERRUPTIVE.value,
    AlertEscalationLevel.URGENT.value,
}

STOP_RE = re.compile(r"^ari,?\s+(stop|pause)$")
RESUME_RE = re.compile(r"^ari,?\s+(resume|start|go)$")
APPROVE_RE = re.compile(r"^(yes|y|yep|yeah|approve|approved|do it|go ahead)(?:\s+(\d+))?$")
SPEND_RE = re.compile(r"^ari,?\s+(spend|spending|cost|costs|usage)\??$")
BUDGET_RE = re.compile(r"^ari,?\s+budget\s+\$?(\d+(?:\.\d+)?)$")
DECLINE_RE = re.compile(r"^(no|n|nope|cancel|decline|don't|dont)(?:\s+(\d+))?$")

Respond = Callable[..., BrainResponse]


@dataclass(slots=True)
class PollReport:
    status: str = "ok"
    detail: str = ""
    handled: int = 0
    replies: list[str] = field(default_factory=list)
    alerts_sent: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "detail": self.detail,
            "handled": self.handled,
            "replies": self.replies,
            "alertsSent": self.alerts_sent,
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
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.action_desk = action_desk
        self.messages_app = messages_app or MessagesApp()
        self.respond = respond
        self.now = now
        self.dry_run = dry_run

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
            history = self._send_alerts(history, report)
            self._save(cursor, history)
        return report

    def _handle(self, row: DumpRow, history: list[dict[str, Any]], report: PollReport) -> list[dict[str, Any]]:
        text = row.text
        if row.is_tapback or not text or _normalize(text) in _recent_replies(history):
            # Reactions are not messages, and in a self-thread ARI's own replies
            # come back looking like Alec's; they are recognized by their text.
            return history
        report.handled += 1
        command = " ".join(text.lower().split()).rstrip(".!")
        # poll_once refuses to run without a reply handle.
        reply_to = row.chat_identifier or self.settings.reply_to or ""

        if STOP_RE.match(command):
            if not self.dry_run:
                pause("Alec texted stop over iMessage.")
            return self._reply(reply_to, history, text, "Paused. Nothing runs until you text \"ARI resume\".", report)
        if RESUME_RE.match(command):
            if not self.dry_run:
                resume()
            return self._reply(
                reply_to, history, text, "Resumed. I didn't act on anything you sent while I was paused.", report
            )
        if SPEND_RE.match(command):
            with self.session_factory() as session:
                return self._reply(reply_to, history, text, month_spend(session).describe(), report)
        budget = BUDGET_RE.match(command)
        if budget:
            if not self.dry_run:
                set_monthly_budget_usd(float(budget.group(1)))
            return self._reply(reply_to, history, text, f"Monthly budget set to ${float(budget.group(1)):.2f}.", report)
        if get_pause_state()["paused"]:
            return history

        approval = APPROVE_RE.match(command) or DECLINE_RE.match(command)
        pending = self.action_desk.pending() if self.action_desk else []
        if approval and pending:
            return self._reply(reply_to, history, text, self._decide(approval, pending), report)

        with self.session_factory() as session:
            spend = month_spend(session)
            recent_requests = requests_since(session, self.now() - LOOP_WINDOW)
        if recent_requests >= LOOP_MAX_REQUESTS:
            # Whatever the cause, a runaway exchange stops here instead of burning tokens.
            if not self.dry_run:
                pause(f"ARI paused itself: {recent_requests} model requests in 10 minutes looks like a loop.")
            return self._reply(
                reply_to,
                history,
                text,
                f"I paused myself: {recent_requests} model requests in the last 10 minutes looks like a loop. "
                "Text \"ARI resume\" when you want me back.",
                report,
            )
        if spend.exhausted:
            return self._reply(
                reply_to,
                history,
                text,
                f"I've used this month's ${spend.budget_usd:.2f} budget, so I'm not calling a model. "
                "Text \"ARI budget\" with a new amount to raise it.",
                report,
            )

        dispatch = make_tool_dispatcher(
            self.session_factory,
            save_for_later=self._save_for_later,
            propose_action=self._propose if self.action_desk else None,
            dry_run=self.dry_run,
        )
        response = self.respond(
            text=text,
            history=history,
            dispatch_tool=dispatch,
            get_mcp_request_args=self._mcp_request_args,
            log_invocation=self._log_invocation,
            record_call=self._record_call,
        )
        if response.reply:
            self._send(reply_to, response.reply, report)
        return response.messages

    def _decide(self, match: re.Match[str], pending: list[PendingProposal]) -> str:
        assert self.action_desk is not None
        approving = APPROVE_RE.match(match.group(0)) is not None
        number = match.group(2)
        if number is None and len(pending) > 1:
            listing = "; ".join(f"{index}) {item.summary}" for index, item in enumerate(pending, start=1))
            verb = "yes" if approving else "no"
            return f"{len(pending)} things are waiting: {listing}. Reply \"{verb} 1\" or similar."
        index = int(number) - 1 if number else 0
        if not 0 <= index < len(pending):
            return f"There's no item {number}. {len(pending)} waiting."
        proposal = pending[index]
        if self.dry_run:
            return f"(dry run) Would {'approve' if approving else 'decline'}: {proposal.summary}"
        if not approving:
            self.action_desk.decline(proposal.task_id, reason="Alec declined over iMessage.")
            return f"Cancelled: {proposal.summary}"
        step = self.action_desk.approve(
            proposal.task_id, approved_by="alec", reason="Approved by reply over iMessage."
        )
        return describe_result(step)

    def _propose(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        assert self.action_desk is not None
        return self.action_desk.propose(tool_input, surface=SURFACE)

    def _send_alerts(self, history: list[dict[str, Any]], report: PollReport) -> list[dict[str, Any]]:
        if get_pause_state()["paused"]:
            return history
        now = self.now()
        with self.session_factory() as session:
            rows = session.scalars(
                select(AlertRow).where(AlertRow.sent_at.is_(None), AlertRow.escalation_level.in_(NOTIFY_LEVELS))
            ).all()
            for alert in sorted(rows, key=lambda row: _utc(row.created_at)):
                if now - _utc(alert.created_at) > ALERT_LOOKBACK:
                    continue
                if alert.escalation_level != AlertEscalationLevel.URGENT.value and self._quiet(now):
                    continue
                body = f"{alert.title}. {alert.reason or alert.message}".strip()
                if self._send(self.settings.reply_to or "", body, report) and not self.dry_run:
                    alert.sent_at = now
                    alert.status = AlertStatus.SENT.value
                    report.alerts_sent += 1
                    # Kept in the conversation so a reply like "why?" has context.
                    history = [*history, {"role": "assistant", "content": [{"type": "text", "text": body}]}] if history else history
            if not self.dry_run:
                session.commit()
        return history

    def _quiet(self, now: datetime) -> bool:
        if self.settings.quiet_hours is None:
            return False
        start, end = self.settings.quiet_hours
        hour = now.astimezone().hour
        if start > end:  # wraps past midnight, e.g. 22-7
            return hour >= start or hour < end
        return start <= hour < end

    def _reply(
        self,
        handle: str,
        history: list[dict[str, Any]],
        text: str,
        reply: str,
        report: PollReport,
    ) -> list[dict[str, Any]]:
        self._send(handle, reply, report)
        # Appended, never edited, so the brain's earlier thinking stays valid.
        return [
            *history,
            {"role": "user", "content": text},
            {"role": "assistant", "content": [{"type": "text", "text": reply}]},
        ]

    def _send(self, handle: str, body: str, report: PollReport) -> bool:
        report.replies.append(body)
        if self.dry_run:
            return True
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

    def _record_call(self, call: ModelCall, deep: bool) -> None:
        # Recorded even in a dry run: the model was really called and really billed.
        with self.session_factory() as session:
            record_model_call(session, call, channel=CHANNEL, escalated=deep)

    def _mcp_request_args(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with self.session_factory() as session:
            return build_mcp_request_args(session)

    def _log_invocation(self, skill_kind, skill_name, tool_name, summary, payload, is_error) -> None:  # type: ignore[no-untyped-def]
        if self.dry_run:
            return
        with self.session_factory() as session:
            record_skill_invocation(
                session,
                channel=CHANNEL,
                skill_kind=skill_kind,
                skill_name=skill_name,
                tool_name=tool_name,
                summary=summary,
                payload=payload,
                is_error=is_error,
            )

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


def _utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; ARI stores UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)
