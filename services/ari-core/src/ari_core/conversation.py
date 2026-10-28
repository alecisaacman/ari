"""One turn of a conversation with ARI, the same on every surface.

Surfaces (iMessage, the hub) only carry text in and out. What a message means is
decided here, in order:

1. control commands ("ARI stop", "ARI resume") pause or resume ARI;
2. while paused, nothing else is acted on;
3. "ARI spend" and "ARI budget N" report or set the monthly model budget;
4. a "yes" or "no" with a proposal waiting approves or declines it. That is
   decided from Alec's own words, never by the model;
5. anything else goes to ARI's brain, unless this month's budget is used up or
   the request rate looks like a loop.

None of the first four calls a model.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import anthropic
from sqlalchemy.orm import Session, sessionmaker

from ari_core.action_desk import ActionDesk, PendingProposal, describe_result
from ari_core.apple import AppleDesk
from ari_core.brain import BrainResponse, make_tool_dispatcher, respond_to_message, roll_history
from ari_core.brain_usage import (
    ModelCall,
    month_spend,
    record_model_call,
    requests_since,
    set_monthly_budget_usd,
)
from ari_core.core import paths as core_paths
from ari_core.core.pause import get_pause_state, pause, resume
from ari_core.memory import get_conversation_state, save_conversation_state
from ari_core.skills import build_mcp_request_args, record_skill_invocation

# Circuit breaker: a burst of model requests this large is a loop, not Alec typing.
# Each message takes one to four requests, so this allows a fast exchange.
LOOP_WINDOW = timedelta(minutes=10)
LOOP_MAX_REQUESTS = 30

STOP_RE = re.compile(r"^ari,?\s+(stop|pause)$")
RESUME_RE = re.compile(r"^ari,?\s+(resume|start|go)$")
APPROVE_RE = re.compile(r"^(yes|y|yep|yeah|approve|approved|do it|go ahead)(?:\s+(\d+))?$")
SPEND_RE = re.compile(r"^ari,?\s+(spend|spending|cost|costs|usage)\??$")
BUDGET_RE = re.compile(r"^ari,?\s+budget\s+\$?(\d+(?:\.\d+)?)$")
DECLINE_RE = re.compile(r"^(no|n|nope|cancel|decline|don't|dont)(?:\s+(\d+))?$")

OUT_OF_CREDITS = (
    "I can't think right now: your Anthropic API credits have run out. Top up at "
    "console.anthropic.com, then text me again. Nothing you sent was lost."
)
KEY_REJECTED = (
    "I can't think right now: Anthropic rejected my API key. Check ANTHROPIC_API_KEY in "
    "~/ARI/ari.env, then text me again."
)

Respond = Callable[..., BrainResponse]

# One turn at a time per process, so a channel's conversation is never written by
# two turns at once.
_TURN_LOCK = threading.Lock()


def save_link_for_later(link: str, note: str | None) -> None:
    """Keep a link Alec wants to watch or read later, in ARI's state."""
    saved = core_paths.ARI_ROOT / "state" / "watch-later.md"
    saved.parent.mkdir(parents=True, exist_ok=True)
    suffix = f" - {note}" if note else ""
    with saved.open("a", encoding="utf-8") as handle:
        handle.write(f"- [{datetime.now(tz=UTC).isoformat()}] {link}{suffix}\n")


@dataclass(frozen=True, slots=True)
class Turn:
    reply: str | None  # None when ARI has nothing to say (paused, or the brain chose not to)
    messages: list[dict[str, Any]]  # the conversation to keep, append-only


class Conversation:
    """A channel's conversation with ARI's one brain."""

    def __init__(
        self,
        *,
        channel: str,
        session_factory: sessionmaker[Session],
        action_desk: ActionDesk | None,
        save_for_later: Callable[[str, str | None], None] = save_link_for_later,
        respond: Respond = respond_to_message,
        now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
        dry_run: bool = False,
        apple: AppleDesk | None = None,
    ) -> None:
        self.channel = channel
        self.apple = apple
        self.session_factory = session_factory
        self.action_desk = action_desk
        self.save_for_later = save_for_later
        self.respond = respond
        self.now = now
        self.dry_run = dry_run

    def say(self, text: str) -> Turn:
        """Take a turn in this channel's stored conversation, and keep the result.

        For surfaces without their own cursor, such as the hub. iMessage keeps its
        cursor alongside the conversation and calls take() itself.
        """
        with _TURN_LOCK:
            with self.session_factory() as session:
                state = get_conversation_state(session, channel=self.channel)
            history = [] if state is None else list(state.messages)
            turn = self.take(text, history)
            if not self.dry_run:
                with self.session_factory() as session:
                    cursor = 0 if state is None else state.cursor
                    save_conversation_state(
                        session, channel=self.channel, cursor=cursor, messages=roll_history(turn.messages)
                    )
            return turn

    def take(self, text: str, history: list[dict[str, Any]]) -> Turn:
        command = " ".join(text.lower().split()).rstrip(".!")

        if STOP_RE.match(command):
            if not self.dry_run:
                pause(f"Alec said stop ({self.channel}).")
            return self._said(history, text, "Paused. Nothing runs until you say \"ARI resume\".")
        if RESUME_RE.match(command):
            if not self.dry_run:
                resume()
            return self._said(history, text, "Resumed. I didn't act on anything you sent while I was paused.")
        if SPEND_RE.match(command):
            with self.session_factory() as session:
                return self._said(history, text, month_spend(session).describe())
        budget = BUDGET_RE.match(command)
        if budget:
            if not self.dry_run:
                set_monthly_budget_usd(float(budget.group(1)))
            return self._said(history, text, f"Monthly budget set to ${float(budget.group(1)):.2f}.")
        if get_pause_state()["paused"]:
            return Turn(reply=None, messages=history)

        approval = APPROVE_RE.match(command) or DECLINE_RE.match(command)
        pending = self.action_desk.pending() if self.action_desk else []
        if approval and pending:
            return self._said(history, text, self._decide(approval, pending))

        with self.session_factory() as session:
            spend = month_spend(session)
            recent_requests = requests_since(session, self.now() - LOOP_WINDOW)
        if recent_requests >= LOOP_MAX_REQUESTS:
            # Whatever the cause, a runaway exchange stops here instead of burning tokens.
            if not self.dry_run:
                pause(f"ARI paused itself: {recent_requests} model requests in 10 minutes looks like a loop.")
            return self._said(
                history,
                text,
                f"I paused myself: {recent_requests} model requests in the last 10 minutes looks like a loop. "
                "Say \"ARI resume\" when you want me back.",
            )
        if spend.exhausted:
            return self._said(
                history,
                text,
                f"I've used this month's ${spend.budget_usd:.2f} budget, so I'm not calling a model. "
                "Say \"ARI budget\" with a new amount to raise it.",
            )

        dispatch = make_tool_dispatcher(
            self.session_factory,
            save_for_later=self.save_for_later,
            propose_action=self._propose if self.action_desk else None,
            dry_run=self.dry_run,
            apple=self.apple,
        )
        try:
            response = self.respond(
                text=text,
                history=history,
                dispatch_tool=dispatch,
                get_mcp_request_args=self._mcp_request_args,
                log_invocation=self._log_invocation,
                record_call=self._record_call,
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            return self._said(history, text, KEY_REJECTED)
        except anthropic.BadRequestError as error:
            if "credit balance" not in str(error).lower():
                raise
            # Retrying can't help until Alec tops up, so say so instead of going silent.
            return self._said(history, text, OUT_OF_CREDITS)
        return Turn(reply=response.reply, messages=response.messages)

    def _said(self, history: list[dict[str, Any]], text: str, reply: str) -> Turn:
        # Appended, never edited, so the brain's earlier thinking stays valid.
        return Turn(
            reply=reply,
            messages=[
                *history,
                {"role": "user", "content": text},
                {"role": "assistant", "content": [{"type": "text", "text": reply}]},
            ],
        )

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
            self.action_desk.decline(proposal.task_id, reason=f"Alec declined ({self.channel}).")
            return f"Cancelled: {proposal.summary}"
        step = self.action_desk.approve(proposal.task_id, approved_by="alec", reason=f"Approved by Alec ({self.channel}).")
        return describe_result(step)

    def _propose(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        assert self.action_desk is not None
        return self.action_desk.propose(tool_input, surface=self.channel)

    def _record_call(self, call: ModelCall, deep: bool) -> None:
        # Recorded even in a dry run: the model was really called and really billed.
        with self.session_factory() as session:
            record_model_call(session, call, channel=self.channel, escalated=deep)

    def _mcp_request_args(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with self.session_factory() as session:
            return build_mcp_request_args(session)

    def _log_invocation(self, skill_kind, skill_name, tool_name, summary, payload, is_error) -> None:  # type: ignore[no-untyped-def]
        if self.dry_run:
            return
        with self.session_factory() as session:
            record_skill_invocation(
                session,
                channel=self.channel,
                skill_kind=skill_kind,
                skill_name=skill_name,
                tool_name=tool_name,
                summary=summary,
                payload=payload,
                is_error=is_error,
            )
