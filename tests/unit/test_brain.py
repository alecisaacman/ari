from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ari_core import brain
from ari_core.brain import roll_history


@dataclass
class Block:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    thinking: str | None = None
    signature: str | None = None

    def model_dump(self, exclude_none: bool = False) -> dict[str, Any]:
        data = {
            "type": self.type,
            "text": self.text or None,
            "id": self.id or None,
            "name": self.name or None,
            "input": self.input or None,
            "thinking": self.thinking,
            "signature": self.signature,
        }
        return {key: value for key, value in data.items() if value is not None or not exclude_none}


@dataclass
class Response:
    content: list[Block]
    stop_reason: str


class FakeClient:
    def __init__(self, responses: list[Response]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.beta = self
        self.messages = self

    def create(self, **kwargs: Any) -> Response:
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


def no_tools(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    raise AssertionError("no tool expected")


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    server_tool_use: Any = None


def test_routine_message_is_answered_by_haiku_with_caching_and_no_fallback() -> None:
    client = FakeClient([Response([Block("text", text="Nothing urgent today.")], "end_turn")])

    result = brain.respond_to_message(text="anything urgent?", history=[], dispatch_tool=no_tools, client=client)

    request = client.requests[0]
    assert result.reply == "Nothing urgent today."
    assert request["model"] == "claude-haiku-5-5"
    assert request["output_config"] == {"effort": "low"}
    assert request["cache_control"] == {"type": "ephemeral"}
    assert request["thinking"] == {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}
    assert "fallbacks" not in request  # Haiku has no server-side fallback
    names = {tool["name"] for tool in request["tools"]}
    assert brain.ESCALATE_TOOL_NAME in names
    assert {"propose_action", "web_search"}.isdisjoint(names)
    assert request["max_tokens"] >= 16000


def test_haiku_hands_the_turn_to_sonnet_which_answers_it_from_a_clean_start() -> None:
    client = FakeClient(
        [
            Response([Block("tool_use", id="e1", name=brain.ESCALATE_TOOL_NAME, input={"reason": "research"})], "tool_use"),
            Response([Block("text", text="Stripe froze hiring in March.")], "end_turn"),
        ]
    )
    calls: list[tuple[str, bool]] = []

    result = brain.respond_to_message(
        text="is Stripe still hiring?",
        history=[],
        dispatch_tool=no_tools,
        client=client,
        record_call=lambda call, deep: calls.append((call.model, deep)),
    )

    fast, deep = client.requests
    assert deep["model"] == "claude-sonnet-5-5"
    assert deep["fallbacks"] == "default"
    assert brain.FALLBACK_BETA in deep["betas"]
    assert {"type": "web_search_20260209", "name": "web_search", "max_uses": 2} in deep["tools"]
    # Sonnet sees the conversation and Alec's message, not Haiku's abandoned turn.
    assert deep["messages"] == fast["messages"]
    assert result.reply == "Stripe froze hiring in March."
    assert [deep_flag for _, deep_flag in calls] == [False, True]
    assert all(message["role"] != "assistant" or message["content"][0].get("name") != brain.ESCALATE_TOOL_NAME
               for message in result.messages)


def test_alec_can_ask_for_the_deeper_model_directly() -> None:
    client = FakeClient([Response([Block("text", text="Here's a plan.")], "end_turn")])

    brain.respond_to_message(text="think: how should I prep for Friday?", history=[], dispatch_tool=no_tools, client=client)

    assert [request["model"] for request in client.requests] == ["claude-sonnet-5-5"]


def test_each_request_is_costed_from_its_usage() -> None:
    response = Response([Block("text", text="ok")], "end_turn")
    response.model = "claude-haiku-5-5"  # type: ignore[attr-defined]
    response.usage = Usage(input_tokens=1_000, output_tokens=200, cache_read_input_tokens=4_000)  # type: ignore[attr-defined]
    recorded = []

    brain.respond_to_message(
        text="hi", history=[], dispatch_tool=no_tools, client=FakeClient([response]),
        record_call=lambda call, deep: recorded.append(call),
    )

    # 1,000 x $0.10 + 4,000 x $0.01 + 200 x $0.50 per million tokens
    assert abs(recorded[0].cost_usd - 0.00024) < 1e-9


def test_tool_results_are_fed_back_and_thinking_is_replayed_unchanged() -> None:
    thinking = Block("thinking", thinking="", signature="sig-1")
    client = FakeClient(
        [
            Response([thinking, Block("tool_use", id="t1", name="get_open_loops")], "tool_use"),
            Response([Block("text", text="One loop: call Sam.")], "end_turn"),
        ]
    )
    calls: list[str] = []

    def dispatch(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(name)
        return {"open_loops": [{"title": "call Sam"}]}

    result = brain.respond_to_message(text="what's open?", history=[], dispatch_tool=dispatch, client=client)
    assert client.requests[1]["model"] == "claude-haiku-5-5"

    assert calls == ["get_open_loops"]
    assert result.reply == "One loop: call Sam."
    replayed = client.requests[1]["messages"][1]["content"][0]
    assert replayed == {"type": "thinking", "thinking": "", "signature": "sig-1"}


def test_paused_server_tool_turn_is_resumed_not_answered_early() -> None:
    client = FakeClient(
        [
            Response([Block("text", text="Searching")], "pause_turn"),
            Response([Block("text", text="Found it.")], "end_turn"),
        ]
    )

    result = brain.respond_to_message(text="research: look this up", history=[], dispatch_tool=no_tools, client=client)

    assert result.reply == "Found it."
    assert len(client.requests) == 2


def test_refusal_gets_a_plain_reply() -> None:
    client = FakeClient([Response([], "refusal")])

    result = brain.respond_to_message(text="x", history=[], dispatch_tool=no_tools, client=client)

    assert result.reply == brain.REFUSAL_REPLY


def test_proposals_are_refused_without_a_workspace() -> None:
    dispatch = brain.make_tool_dispatcher(lambda: None, save_for_later=lambda link, note: None)  # type: ignore[arg-type,return-value]

    assert "error" in dispatch("propose_action", {"action_type": "write_file", "summary": "x"})


def test_history_is_append_only_until_it_rolls() -> None:
    short = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": [{"type": "text", "text": "hey"}]}]
    assert roll_history(short) is short


def test_rolled_history_starts_at_alec_and_drops_thinking_once() -> None:
    history: list[dict[str, Any]] = []
    for index in range(40):
        history.append({"role": "user", "content": [{"type": "text", "text": f"message {index}"}]})
        history.append(
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "", "signature": f"s{index}"},
                    {"type": "tool_use", "id": f"t{index}", "name": "get_open_loops", "input": {}},
                ],
            }
        )
        history.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{index}", "content": "{}"}]})

    rolled = roll_history(history)

    assert len(rolled) <= brain.ROLLED_HISTORY_MESSAGES + 2
    assert rolled[0]["role"] == "user" and rolled[0]["content"][0]["type"] == "text"
    assert all(
        block.get("type") != "thinking"
        for message in rolled
        if message["role"] == "assistant"
        for block in message["content"]
    )
    assert roll_history(rolled) is rolled


def test_cold_cache_cost_bills_cached_tokens_as_writes() -> None:
    from ari_core.brain_usage import ModelCall

    call = ModelCall("claude-sonnet-5-5", input_tokens=1_000, output_tokens=100,
                     cache_write_tokens=0, cache_read_tokens=10_000, web_searches=1)

    # warm: 1,000 x $2 + 10,000 x $0.20 + 100 x $10 per million, plus $0.01 search
    assert abs(call.cost_usd - 0.015) < 1e-9
    # cold: the 10,000 cached tokens are written at $2.50 per million instead
    assert abs(call.cold_cost_usd - 0.038) < 1e-9


def test_default_client_cannot_hang_forever() -> None:
    client = brain.make_client()

    assert client.timeout == brain.REQUEST_TIMEOUT_SECONDS
    assert client.max_retries == 2


def test_brain_keeps_and_finds_memory_notes_and_daily_state(tmp_path) -> None:
    from ari_core.state import get_daily_state
    from ari_memory import create_engine, create_session_factory

    session_factory = create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))
    spine = tmp_path / "spine.db"
    dispatch = brain.make_tool_dispatcher(session_factory, save_for_later=lambda link, note: None, spine_db_path=spine)

    dispatch("remember", {"kind": "person", "title": "Sam (internship contact)", "content": "Met at the econ career fair; works at Ramp."})
    dispatch("save_note", {"title": "Ramp call notes", "body": "Sam said the analyst team hires in January."})
    found = dispatch("recall", {"query": "What do I know about Sam at Ramp?"})["found"]
    assert [hit["title"] for hit in found][:2] == ["Sam (internship contact)", "Ramp call notes"] or {
        hit["title"] for hit in found
    } >= {"Sam (internship contact)", "Ramp call notes"}
    assert dispatch("recall", {"query": "zebra"})["found"] == []

    dispatch("set_daily_state", {"priorities": ["Outline section 3"], "win_condition": "Outline done", "stress": 4})
    with session_factory() as session:
        state = get_daily_state(session, day=datetime.now().date())
    assert state is not None and state.priorities == ["Outline section 3"] and state.stress == 4
    assert "hub_tasks" in dispatch("get_open_loops", {})


def _dispatcher(tmp_path):
    from ari_memory import create_engine, create_session_factory

    session_factory = create_session_factory(create_engine(f"sqlite+pysqlite:///{tmp_path / 'ari.db'}"))
    dispatch = brain.make_tool_dispatcher(
        session_factory, save_for_later=lambda link, note: None, spine_db_path=tmp_path / "spine.db"
    )
    return session_factory, dispatch


def test_talking_about_an_open_loop_again_adds_to_it_instead_of_filing_it_twice(tmp_path) -> None:
    _, dispatch = _dispatcher(tmp_path)

    first = dispatch("create_open_loop", {"title": "Finish the outline"})["created"]
    again = dispatch("create_open_loop", {"title": "Finish outline for section 3", "notes": "Due Friday"})
    other = dispatch("create_open_loop", {"title": "Call Sam"})

    assert again["already_open"]["id"] == first["id"]
    assert "Finish outline for section 3" in again["already_open"]["notes"]
    assert "Due Friday" in again["already_open"]["notes"]
    assert "created" in other
    loops = dispatch("get_open_loops", {})["open_loops"]
    assert sorted(loop["title"] for loop in loops) == ["Call Sam", "Finish the outline"]

    updated = dispatch("update_open_loop", {"loop_id": first["id"], "note": "Sam wants it by Thursday", "priority": "high"})
    assert updated["updated"]["priority"] == "high"
    assert "Sam wants it by Thursday" in updated["updated"]["notes"]


def test_different_loops_about_the_same_person_stay_separate(tmp_path) -> None:
    _, dispatch = _dispatcher(tmp_path)

    dispatch("create_open_loop", {"title": "Email Sam the deck"})

    assert "created" in dispatch("create_open_loop", {"title": "Call Sam about Ramp"})


def test_reminders_are_set_listed_and_cancelled(tmp_path) -> None:
    from datetime import timedelta

    _, dispatch = _dispatcher(tmp_path)
    at = (datetime.now() + timedelta(hours=2)).replace(microsecond=0).isoformat()

    reminder = dispatch("set_reminder", {"text": "Call Sam", "at": at})["reminder"]
    assert [item["id"] for item in dispatch("list_reminders", {})["reminders"]] == [reminder["id"]]
    assert dispatch("cancel_reminder", {"reminder_id": reminder["id"]})["cancelled"]["status"] == "cancelled"
    assert dispatch("list_reminders", {})["reminders"] == []
    past = (datetime.now() - timedelta(hours=1)).isoformat()
    assert "error" in dispatch("set_reminder", {"text": "Too late", "at": past})


def test_a_live_sqlite_store_gains_new_optional_columns(tmp_path) -> None:
    import sqlite3

    from ari_memory import create_engine

    db = tmp_path / "ari.db"
    create_engine(f"sqlite+pysqlite:///{db}")
    with sqlite3.connect(db) as connection:
        connection.execute("ALTER TABLE reminders DROP COLUMN apple_id")
    create_engine(f"sqlite+pysqlite:///{db}")
    with sqlite3.connect(db) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(reminders)")}
    assert "apple_id" in columns
