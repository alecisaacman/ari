"""ARI's intelligence layer: the single Claude-backed brain behind every ACE
surface. It understands free text (today arriving over iMessage), grounds its
answers and actions in real ARI state through tool use, and never invents what
it doesn't know.

Surfaces never reason on their own; they hand text here. Conversation history
is the caller's responsibility to persist across turns: this module is
stateless per call, and `roll_history` keeps a persisted history valid.

The brain only proposes changes outside ARI's own records (`propose_action`).
Approval is Alec's, taken deterministically by the surface, and execution goes
through ARI's canonical execution gateway.
"""
from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import anthropic
from ari_state import OpenLoop, OpenLoopKind, OpenLoopPriority, SkillKind
from sqlalchemy.orm import Session

from ari_core.brain_usage import ModelCall
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

# Haiku answers first; it hands a message to the deeper model when it needs
# research, drafting, judgment, or a workspace change, or when Alec asks.
FAST_MODEL = os.environ.get("ARI_BRAIN_FAST_MODEL", "claude-haiku-5-5")
DEEP_MODEL = os.environ.get("ARI_BRAIN_DEEP_MODEL", os.environ.get("ARI_BRAIN_MODEL", "claude-sonnet-5-5"))
FAST_EFFORT = os.environ.get("ARI_BRAIN_FAST_EFFORT", "low")
DEEP_EFFORT = os.environ.get("ARI_BRAIN_DEEP_EFFORT", "medium")
# Thinking tokens count against this, so it is far above a text reply's length.
MAX_TOKENS = 16000
NO_REPLY_SENTINEL = "NO_REPLY"
MAX_TOOL_TURNS = 6
# Server-side refusal fallback for the deep model: if it declines, another model
# answers instead of ARI going silent. Haiku has no server-side fallback.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# The two models get different tools, and each model's thinking blocks are bound
# to the request that produced them. Dropping a mismatched block is the documented
# alternative to a 400, so a model switch just loses the other model's reasoning.
BINDING_BETA = "thinking-binding-controls-2026-08-01"
ESCALATE_TOOL_NAME = "use_deeper_model"
# Alec can ask for the deeper model directly: "think: ...", "research: ...".
DEEP_REQUEST_RE = re.compile(r"^(think|think hard|deep|research)\s*[:,-]", re.IGNORECASE)
LONG_MESSAGE_CHARS = 600
# A request that hangs (a dropped connection, a sleeping Mac) must fail instead of
# freezing the surface that is waiting on it. Web search turns take about 15 s.
REQUEST_TIMEOUT_SECONDS = 90.0


def make_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(timeout=REQUEST_TIMEOUT_SECONDS, max_retries=2)
REFUSAL_REPLY = "I can't help with that one."
# A persisted conversation stays append-only until it passes this many messages.
MAX_HISTORY_MESSAGES = 60
ROLLED_HISTORY_MESSAGES = 20

# Bound by the caller (e.g. scripts/imessage-ingest.py) to a real session
# factory, the same way dispatch_tool is bound via make_tool_dispatcher --
# this module stays decoupled from ari_memory/Postgres specifics.
GetMcpRequestArgs = Callable[[], tuple[list[dict[str, Any]], list[dict[str, Any]]]]
LogInvocation = Callable[[SkillKind, str, str, str, dict[str, Any], bool], None]
# Receives every model request's usage, and whether the deeper model served it.
RecordCall = Callable[[ModelCall, bool], None]


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

You keep two kinds of things. Alec's open loops, notes, and saved links are your own \
records: update them directly with your tools. Anything that changes something outside \
those records, such as writing or editing a file in Alec's workspace or running tests, \
goes through propose_action. You cannot approve a proposal yourself. ARI shows it to \
Alec, who approves by replying "yes" or declines with "no". After proposing, tell him \
in one or two plain sentences exactly what will happen if he approves. Never say it is \
done until ARI reports the result.

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

FAST_SYSTEM_ADDENDUM = f"""

You are ARI's fast model. You handle Alec's records yourself: reading his open \
loops and state, and capturing, resolving, or saving things. Call {ESCALATE_TOOL_NAME} \
instead of answering when a message needs: looking anything up on the web, research, \
drafting or writing, planning, analysis or comparisons, explaining why, any change to \
files or running tests, or when you are not confident you can answer it well. You \
don't have tools for those; ARI's deeper model does.
"""

ESCALATE_TOOL: dict[str, Any] = {
    "name": ESCALATE_TOOL_NAME,
    "description": (
        "Hand this message to ARI's deeper model, which can search the web, draft, plan, "
        "analyze, and propose workspace changes. Say briefly why."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"reason": {"type": "string"}},
        "required": ["reason"],
    },
}

WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20260209",
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
        "name": "propose_action",
        "description": (
            "Propose one change in Alec's workspace for his approval: write_file, "
            "patch_file, or run_command (only ls, cat, pytest, or node --check/--test). "
            "Nothing runs until Alec approves it. Paths are relative to the workspace."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": ["write_file", "patch_file", "run_command"],
                },
                "path": {"type": "string", "description": "For write_file and patch_file."},
                "content": {"type": "string", "description": "Full new content, for write_file."},
                "find": {"type": "string", "description": "Exact text to replace, for patch_file."},
                "replace": {"type": "string", "description": "Replacement text, for patch_file."},
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Argument list, for run_command, e.g. [\"pytest\", \"tests\", \"-q\"].",
                },
                "summary": {
                    "type": "string",
                    "description": "One plain sentence Alec will read before approving.",
                },
            },
            "required": ["action_type", "summary"],
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


ProposeAction = Callable[[dict[str, Any]], dict[str, Any]]


def make_tool_dispatcher(
    session_factory: Callable[[], Session],
    *,
    save_for_later: Callable[[str, str | None], None],
    propose_action: ProposeAction | None = None,
    dry_run: bool = False,
) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """Build a tool dispatcher bound to a session factory and a save-for-later sink.

    With dry_run=True, mutating tools (create_open_loop, resolve_open_loop,
    save_for_later, propose_action) report what they would have done without
    touching the database, the save_for_later sink, or the execution ledger.
    Read tools still hit the real database, since previewing requires seeing
    real state. Without a propose_action sink, proposals are refused.
    """

    def dispatch(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        if name == "propose_action":
            if dry_run:
                return {"proposed": {"summary": tool_input.get("summary"), "dry_run": True}}
            if propose_action is None:
                return {"error": "No workspace is configured for actions."}
            return propose_action(tool_input)
        if dry_run and name == "create_open_loop":
            return {"created": {"title": tool_input["title"], "dry_run": True}}
        if dry_run and name == "resolve_open_loop":
            return {"resolved": {"loop_id": tool_input["loop_id"], "dry_run": True}}
        if dry_run and name == "save_for_later":
            return {"saved": tool_input["link"], "dry_run": True}

        with session_factory() as session:
            if name == "get_open_loops":
                loops = list_open_loops(session)
                return {"open_loops": [_serialize_loop(loop) for loop in loops]}

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


FAST_TOOL_NAMES = {
    "get_open_loops",
    "get_daily_state",
    "get_weekly_state",
    "get_recent_signals_and_alerts",
    "create_open_loop",
    "resolve_open_loop",
    "save_for_later",
}
FAST_TOOLS: list[dict[str, Any]] = [tool for tool in TOOLS if tool["name"] in FAST_TOOL_NAMES] + [ESCALATE_TOOL]


def roll_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a persisted conversation that the next request can replay.

    Thinking blocks are bound to the exact conversation that produced them, so
    the history stays append-only. Once it passes MAX_HISTORY_MESSAGES it rolls:
    it keeps the most recent turns, starting at one of Alec's own messages, and
    strips every thinking block from them once, at that boundary.
    """
    if len(messages) <= MAX_HISTORY_MESSAGES:
        return messages
    starts = [index for index, message in enumerate(messages) if _is_alec_message(message)]
    cutoff = len(messages) - ROLLED_HISTORY_MESSAGES
    start = next((index for index in starts if index >= cutoff), None)
    if start is None:
        start = starts[-1] if starts else len(messages)
    return [_without_thinking(message) for message in messages[start:]]


def _is_alec_message(message: dict[str, Any]) -> bool:
    """A user turn Alec wrote, as opposed to one carrying tool results."""
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if isinstance(content, str):
        return True
    return isinstance(content, list) and not any(
        isinstance(block, dict) and block.get("type") == "tool_result" for block in content
    )


def _without_thinking(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    if message.get("role") != "assistant" or not isinstance(content, list):
        return message
    kept = [
        block
        for block in content
        if not (isinstance(block, dict) and block.get("type") in {"thinking", "redacted_thinking"})
    ]
    return {**message, "content": kept}


@dataclass(frozen=True, slots=True)
class _ModelConfig:
    model: str
    effort: str
    system: str
    tools: list[dict[str, Any]]
    mcp_servers: list[dict[str, Any]]
    deep: bool


def respond_to_message(
    *,
    text: str,
    history: list[dict[str, Any]],
    dispatch_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
    model: str | None = None,
    get_mcp_request_args: GetMcpRequestArgs = _no_mcp_servers,
    log_invocation: LogInvocation = _no_op_log_invocation,
    record_call: RecordCall | None = None,
    client: Any | None = None,
    now: datetime | None = None,
) -> BrainResponse:
    """Answer one message from Alec, running any tools the model calls.

    The fast model answers first. If it calls use_deeper_model, or Alec asked
    for depth, the whole turn is answered by the deep model instead; the fast
    model's partial turn is discarded, and its cost is still recorded. Passing
    `model` pins one model with the deep model's tools.

    get_mcp_request_args and log_invocation default to no-ops, so callers that
    don't pass them get no MCP servers and no skill audit rows.
    """
    client = client or make_client()
    sent_at = (now or datetime.now(tz=UTC)).astimezone().strftime("%A %B %-d, %Y, %-I:%M %p %Z")
    user_turn = {
        "role": "user",
        # The time rides with the message, so the system prompt stays cacheable.
        "content": [{"type": "text", "text": text}, {"type": "text", "text": f"(Sent {sent_at}.)"}],
    }
    base = [*history, user_turn]

    # Fetched once per message: which MCP servers are enabled doesn't change
    # mid-conversation. Skills are offered only to the deep model.
    mcp_servers, mcp_tools = get_mcp_request_args()
    deep = _ModelConfig(
        model=model or DEEP_MODEL,
        effort=DEEP_EFFORT,
        system=SYSTEM_PROMPT,
        tools=[*TOOLS, WEB_SEARCH_TOOL, *mcp_tools],
        mcp_servers=mcp_servers,
        deep=True,
    )
    wants_depth = bool(DEEP_REQUEST_RE.match(text.strip())) or len(text) > LONG_MESSAGE_CHARS
    if model is None and not wants_depth:
        fast = _ModelConfig(
            model=FAST_MODEL,
            effort=FAST_EFFORT,
            system=SYSTEM_PROMPT + FAST_SYSTEM_ADDENDUM,
            tools=FAST_TOOLS,
            mcp_servers=[],
            deep=False,
        )
        answered = _run_turn(client, fast, base, dispatch_tool, log_invocation, record_call)
        if answered is not None:
            return answered
    answered = _run_turn(client, deep, base, dispatch_tool, log_invocation, record_call)
    assert answered is not None  # the deep model has no escalation tool
    return answered


def _run_turn(
    client: Any,
    config: _ModelConfig,
    base: list[dict[str, Any]],
    dispatch_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
    log_invocation: LogInvocation,
    record_call: RecordCall | None,
) -> BrainResponse | None:
    """Run one model's tool loop. None means the fast model asked to escalate."""
    messages = list(base)
    betas = [BINDING_BETA]
    extra: dict[str, Any] = {}
    if config.model.startswith(("claude-sonnet", "claude-opus")):
        betas.append(FALLBACK_BETA)
        extra["fallbacks"] = "default"
    if config.mcp_servers:
        betas.append(MCP_BETA_HEADER)
        extra["mcp_servers"] = config.mcp_servers

    for _ in range(MAX_TOOL_TURNS):
        response = client.beta.messages.create(
            model=config.model,
            max_tokens=MAX_TOKENS,
            system=config.system,
            tools=config.tools,
            messages=messages,
            thinking={"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}},
            output_config={"effort": config.effort},
            # Caches the system prompt, tools, and conversation so far.
            cache_control={"type": "ephemeral"},
            betas=betas,
            **extra,
        )
        if record_call is not None:
            record_call(ModelCall.from_response(response), config.deep)
        assistant_content = [block.model_dump(exclude_none=True) for block in response.content]

        if any(block.type == "tool_use" and block.name == ESCALATE_TOOL_NAME for block in response.content):
            return None
        messages.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason == "refusal":
            return BrainResponse(reply=REFUSAL_REPLY, messages=messages)
        if response.stop_reason == "pause_turn":
            # A long server-side tool turn (web search) paused; resend to continue it.
            continue

        # web_search and MCP tools run server-side inside this same API call --
        # only client-side tools show up as tool_use blocks needing dispatch_tool.
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
