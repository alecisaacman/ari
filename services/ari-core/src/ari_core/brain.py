"""ARI's intelligence layer: a single Claude-backed brain that understands
free text (currently arriving via iMessage), grounds its answers and actions
in real ARI state through tool use, and never invents what it doesn't know.

This replaces hand-rolled classification heuristics (regex/keyword matching)
with actual understanding. Conversation history is the caller's
responsibility to persist across turns — this module is stateless per call.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import anthropic
from ari_state import OpenLoop, OpenLoopKind, OpenLoopPriority, SkillKind
from sqlalchemy.orm import Session

from ari_core.history import get_latest_run_details
from ari_core.skills import MCP_BETA_HEADER, extract_resolved_skill_invocations
from ari_core.state import (
    CreateOpenLoopInput,
    create_open_loop,
    get_daily_state,
    get_weekly_state,
    list_open_loops,
    resolve_open_loop,
)

DEFAULT_MODEL = os.environ.get("ARI_BRAIN_MODEL", "claude-sonnet-4-6")
NO_REPLY_SENTINEL = "NO_REPLY"
MAX_TOOL_TURNS = 6

# Bound by the caller (e.g. scripts/imessage-ingest.py) to a real session
# factory, the same way dispatch_tool is bound via make_tool_dispatcher --
# this module stays decoupled from ari_memory/Postgres specifics.
GetMcpRequestArgs = Callable[[], tuple[list[dict[str, Any]], list[dict[str, Any]]]]
LogInvocation = Callable[[SkillKind, str, str, str, dict[str, Any], bool], None]


def _no_mcp_servers() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return [], []


def _no_op_log_invocation(
    skill_kind: SkillKind,
    skill_name: str,
    tool_name: str,
    summary: str,
    payload: dict[str, Any],
    is_error: bool,
) -> None:
    return None

SYSTEM_PROMPT = """You are ARI, Alec's personal AI operating system. You are calm, \
direct, and operational — a JARVIS-like presence, not a wellness app. You never use \
exclamation points, emoji, or motivational filler.

You are reached over iMessage, in a thread Alec uses as his own personal notes \
channel. Replies must read like text messages: short, plain text, no markdown.

Ground rule: never invent information about Alec's tasks, schedule, signals, or \
state. Always use your tools to check before answering a question about what's \
going on. If you don't know, say so or ask — do not guess.

How to handle what Alec sends you:
- A link to Instagram, YouTube, or TikTok with no other context is something he \
wants to watch later, not a task. Call save_for_later and reply with exactly \
"NO_REPLY" — no confirmation needed, it doesn't need his attention.
- A clear task, commitment, or list of multiple things to do should be filed with \
create_open_loop — one call per discrete item. Then reply with a short confirmation \
naming exactly what you filed, so Alec can tell you parsed it correctly and aren't \
making things up.
- If Alec says he applied to, submitted an application to, or sent his resume to a \
company, file it with create_open_loop using kind="job_application" and the company \
name in the company field — not kind="task". Filing it this way automatically \
triggers a background company-research pass (layoffs, hiring freezes, funding, \
interview signals), so the company field must be the actual employer name, not the \
job title or a paraphrase.
- A link to something else (a business, an article, a reference) with no stated \
purpose is ambiguous. Do not guess what he wants done with it. Ask him directly what \
it's about or what action he wants taken, in one short question. Wait for his next \
message to answer that — when he replies, combine his answer with the link into a \
single create_open_loop call.
- A question about his current state (what's going on, what's on his plate, how's \
the week) should be answered using get_open_loops / get_daily_state / get_weekly_state \
/ get_recent_signals_and_alerts. Cite what you actually found. If there's nothing, say \
there's nothing rather than inventing an answer.
- If asked to resolve, close, or mark something done, use resolve_open_loop — you'll \
need the loop's id, which you get from get_open_loops first if you don't already have \
it in this conversation.
- You can search the web when it actually helps: a factual question you're not certain \
of, a request to look something up or research a topic, or checking a claim before \
acting on it. Don't search reflexively for every message — only when it changes what \
you'd say or do. If you search, ground your reply in what you actually found; cite it \
plainly (e.g. "found X — source: ...") rather than presenting it as something you \
already knew.

Reply with exactly "NO_REPLY" only for save_for_later cases. Everything else gets a \
real, short reply.
"""

WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 2,
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_open_loops",
        "description": "List Alec's currently active (not resolved) open loops/tasks.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_daily_state",
        "description": "Get Alec's recorded daily state (priorities, stress, win condition) for a date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD). Defaults to today if omitted.",
                }
            },
        },
    },
    {
        "name": "get_weekly_state",
        "description": "Get Alec's recorded weekly plan/reflection for the week containing a date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD) within the target week. Defaults to today.",
                }
            },
        },
    },
    {
        "name": "get_recent_signals_and_alerts",
        "description": "Get the signals and alerts from the latest orchestration run for a date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD). Defaults to today.",
                }
            },
        },
    },
    {
        "name": "create_open_loop",
        "description": (
            "File a new open loop (task/commitment/question/follow-up/job_application) "
            "for Alec. Use kind='job_application' with a company name to trigger "
            "automatic company research."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": [
                        "task",
                        "question",
                        "commitment",
                        "follow_up",
                        "job_application",
                    ],
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
                "notes": {"type": "string"},
                "company": {
                    "type": "string",
                    "description": (
                        "Employer name. Required when kind is 'job_application' — "
                        "triggers automatic company research."
                    ),
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "resolve_open_loop",
        "description": "Mark an open loop as resolved/closed by its id.",
        "input_schema": {
            "type": "object",
            "properties": {"loop_id": {"type": "string"}},
            "required": ["loop_id"],
        },
    },
    {
        "name": "save_for_later",
        "description": "Save a link Alec wants to watch/read later. Does not create a task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "link": {"type": "string"},
                "note": {"type": "string", "description": "Optional surrounding context."},
            },
            "required": ["link"],
        },
    },
]


@dataclass(frozen=True, slots=True)
class BrainResponse:
    reply: str | None  # None if the brain decided no reply is needed
    messages: list[dict[str, Any]]  # updated conversation history to persist


def _serialize_loop(loop: OpenLoop) -> dict[str, Any]:
    return {
        "id": str(loop.id),
        "title": loop.title,
        "kind": loop.kind,
        "priority": loop.priority,
        "status": loop.status,
        "notes": loop.notes,
        "company": loop.company,
        "opened_at": loop.opened_at.isoformat(),
        "last_touched_at": loop.last_touched_at.isoformat() if loop.last_touched_at else None,
    }


def _resolve_date(raw: Any) -> date:
    if isinstance(raw, str) and raw:
        return date.fromisoformat(raw)
    return date.today()


def make_tool_dispatcher(
    session_factory: Callable[[], Session],
    *,
    save_for_later: Callable[[str, str | None], None],
    dry_run: bool = False,
) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """Build a tool dispatcher bound to a session factory and a save-for-later sink.

    With dry_run=True, mutating tools (create_open_loop, resolve_open_loop,
    save_for_later) report what they would have done without touching the
    database or calling the save_for_later sink. Read tools still hit the
    real database, since previewing requires seeing real state.
    """

    def dispatch(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        if dry_run and name == "create_open_loop":
            return {"created": {"title": tool_input["title"], "dry_run": True}}
        if dry_run and name == "resolve_open_loop":
            return {"resolved": {"loop_id": tool_input["loop_id"], "dry_run": True}}
        if dry_run and name == "save_for_later":
            return {"saved": tool_input["link"], "dry_run": True}

        with session_factory() as session:
            if name == "get_open_loops":
                loops = list_open_loops(session)
                return {"open_loops": [_serialize_loop(l) for l in loops]}

            if name == "get_daily_state":
                day = _resolve_date(tool_input.get("date"))
                state = get_daily_state(session, day=day)
                return {"daily_state": state.model_dump(mode="json") if state else None}

            if name == "get_weekly_state":
                day = _resolve_date(tool_input.get("date"))
                state = get_weekly_state(session, state_date=day)
                return {"weekly_state": state.model_dump(mode="json") if state else None}

            if name == "get_recent_signals_and_alerts":
                day = _resolve_date(tool_input.get("date"))
                details = get_latest_run_details(session, state_date=day)
                if details is None:
                    return {"signals": [], "alerts": [], "note": "no orchestration run for this date"}
                return {
                    "signals": [s.model_dump(mode="json") for s in details.signals],
                    "alerts": [a.model_dump(mode="json") for a in details.alerts],
                }

            if name == "create_open_loop":
                loop_input = CreateOpenLoopInput(
                    title=tool_input["title"],
                    source="ari.brain",
                    kind=OpenLoopKind(tool_input.get("kind", "task")),
                    priority=OpenLoopPriority(tool_input.get("priority", "medium")),
                    notes=tool_input.get("notes") or "",
                    company=tool_input.get("company") or None,
                )
                result = create_open_loop(session, loop=loop_input, opened_at=datetime.now(tz=UTC))
                return {"created": _serialize_loop(result.state)}

            if name == "resolve_open_loop":
                result = resolve_open_loop(
                    session,
                    loop_id=UUID(tool_input["loop_id"]),
                    resolved_at=datetime.now(tz=UTC),
                )
                if result is None:
                    return {"error": f"no open loop found with id {tool_input['loop_id']}"}
                return {"resolved": _serialize_loop(result.state)}

            if name == "save_for_later":
                save_for_later(tool_input["link"], tool_input.get("note"))
                return {"saved": tool_input["link"]}

        return {"error": f"unknown tool: {name}"}

    return dispatch


def respond_to_message(
    *,
    text: str,
    history: list[dict[str, Any]],
    dispatch_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
    model: str = DEFAULT_MODEL,
    get_mcp_request_args: GetMcpRequestArgs = _no_mcp_servers,
    log_invocation: LogInvocation = _no_op_log_invocation,
) -> BrainResponse:
    """Send a message to the brain, executing any tool calls it makes, and
    return its final reply plus the updated conversation history.

    get_mcp_request_args and log_invocation default to no-ops, so callers
    that don't pass them (existing tests, anything not yet wired to a
    skill registry) get exactly today's behavior: no MCP servers offered,
    no audit rows written. This is additive — it does not change whether
    or when the brain decides to call a skill, only what's offered to it
    and what gets recorded afterward.
    """
    client = anthropic.Anthropic()
    messages: list[dict[str, Any]] = [*history, {"role": "user", "content": text}]

    # Fetched once per message, not per tool-use turn: which MCP servers are
    # enabled doesn't change mid-conversation, and this avoids a DB round
    # trip on every one of MAX_TOOL_TURNS turns.
    mcp_servers, mcp_tools = get_mcp_request_args()
    all_tools = [*TOOLS, WEB_SEARCH_TOOL, *mcp_tools]

    for _ in range(MAX_TOOL_TURNS):
        if mcp_servers:
            # Only the beta endpoint accepts mcp_servers/betas. Anthropic
            # documents this beta as a strict superset of the stable
            # Messages API, so non-MCP behavior (custom tools, web_search)
            # is unchanged when it's used — confirm this empirically before
            # trusting it in production, not just from the docs.
            response = client.beta.messages.create(
                model=model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=all_tools,
                messages=messages,
                mcp_servers=mcp_servers,
                betas=[MCP_BETA_HEADER],
            )
        else:
            # No skills registered (true in production today): byte-for-byte
            # the same call as before this feature existed.
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=all_tools,
                messages=messages,
            )
        assistant_content = [block.model_dump() for block in response.content]
        messages.append({"role": "assistant", "content": assistant_content})

        # web_search and MCP tools run server-side inside this same API call
        # (Anthropic executes them and feeds results back to Claude before
        # responding) — only client-side tools show up as
        # block.type == "tool_use" here and need dispatch_tool.
        # stop_reason == "tool_use" means a client tool is actually waiting
        # on us, never an already-resolved web_search/MCP call.
        for resolved in extract_resolved_skill_invocations(assistant_content):
            log_invocation(
                resolved["skill_kind"],
                resolved["skill_name"],
                resolved["tool_name"],
                resolved["summary"],
                resolved["payload"],
                resolved["is_error"],
            )

        if response.stop_reason != "tool_use":
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()
            reply = None if final_text == NO_REPLY_SENTINEL else (final_text or None)
            return BrainResponse(reply=reply, messages=messages)

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = dispatch_tool(block.name, block.input)
                log_invocation(
                    SkillKind.CUSTOM_TOOL,
                    "ari.brain",
                    block.name,
                    f"custom_tool:{block.name}",
                    {"input": block.input, "result": result},
                    isinstance(result, dict) and "error" in result,
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    }
                )
        messages.append({"role": "user", "content": tool_results})

    return BrainResponse(
        reply="Something I was asked to do took too many steps — flagging rather than guessing further.",
        messages=messages,
    )
