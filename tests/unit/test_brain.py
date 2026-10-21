from __future__ import annotations

from dataclasses import dataclass, field
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


def test_request_uses_sonnet_5_5_with_fallback_and_low_effort() -> None:
    client = FakeClient([Response([Block("text", text="Nothing urgent today.")], "end_turn")])

    result = brain.respond_to_message(text="anything urgent?", history=[], dispatch_tool=no_tools, client=client)

    request = client.requests[0]
    assert result.reply == "Nothing urgent today."
    assert request["model"] == "claude-sonnet-5-5"
    assert request["fallbacks"] == "default"
    assert brain.FALLBACK_BETA in request["betas"]
    assert request["output_config"] == {"effort": "low"}
    assert request["max_tokens"] >= 16000
    assert "thinking" not in request
    assert {"type": "web_search_20260209", "name": "web_search", "max_uses": 2} in request["tools"]


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

    result = brain.respond_to_message(text="look this up", history=[], dispatch_tool=no_tools, client=client)

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
        history.append({"role": "user", "content": f"message {index}"})
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
    assert rolled[0]["role"] == "user" and isinstance(rolled[0]["content"], str)
    assert all(
        block.get("type") != "thinking"
        for message in rolled
        if message["role"] == "assistant"
        for block in message["content"]
    )
    assert roll_history(rolled) is rolled
