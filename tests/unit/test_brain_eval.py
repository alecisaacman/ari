from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ari_core import brain

EVAL_DIR = Path(__file__).resolve().parents[2] / "evals" / "brain"
_spec = importlib.util.spec_from_file_location("brain_eval", EVAL_DIR / "run_eval.py")
assert _spec is not None and _spec.loader is not None
brain_eval = importlib.util.module_from_spec(_spec)
sys.modules["brain_eval"] = brain_eval  # dataclasses resolve their module by name
_spec.loader.exec_module(brain_eval)


@dataclass
class Block:
    type: str
    text: str = ""
    id: str = "tool-1"
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)

    def model_dump(self, exclude_none: bool = False) -> dict[str, Any]:
        return {"type": self.type, "text": self.text, "id": self.id, "name": self.name, "input": self.input}


@dataclass
class Usage:
    input_tokens: int = 3_000
    output_tokens: int = 150
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    server_tool_use: Any = None


@dataclass
class Response:
    content: list[Block]
    stop_reason: str
    model: str
    usage: Usage = field(default_factory=Usage)


class ScriptedClient:
    """Haiku reads open loops for state questions and escalates research; Sonnet answers."""

    def __init__(self) -> None:
        self.beta = self
        self.messages = self

    def create(self, **request: Any) -> Response:
        model = request["model"]
        last = request["messages"][-1]
        if isinstance(last["content"], list) and last["content"][0].get("type") == "tool_result":
            return Response([Block("text", text="You have the econ paper due Friday.")], "end_turn", model)
        text = last["content"][0]["text"]
        if model == "claude-haiku-5-5" and "hiring" in text:
            return Response([Block("tool_use", name=brain.ESCALATE_TOOL_NAME, input={"reason": "web"})], "tool_use", model)
        if "plate" in text:
            return Response([Block("tool_use", name="get_open_loops")], "tool_use", model)
        return Response([Block("text", text="Ramp is hiring.")], "end_turn", model)


def test_eval_grades_routing_tools_and_cost_against_seeded_state(tmp_path: Path) -> None:
    cases = [case for case in json.loads((EVAL_DIR / "cases.json").read_text()) if case["id"] in {"plate-today", "ramp-hiring"}]

    results = brain_eval.run_eval(cases, client=ScriptedClient(), max_usd=1.0, out_dir=tmp_path)

    by_key = {(result.case_id, result.config): result for result in results}
    assert by_key[("plate-today", "routed")].passed
    assert by_key[("plate-today", "routed")].models == ["claude-haiku-5-5", "claude-haiku-5-5"]
    assert by_key[("ramp-hiring", "routed")].passed
    assert by_key[("ramp-hiring", "routed")].models == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    assert by_key[("ramp-hiring", "sonnet")].models == ["claude-sonnet-5-5"]
    assert by_key[("plate-today", "routed")].cost_usd < by_key[("plate-today", "sonnet")].cost_usd
    report = (tmp_path / "report.md").read_text()
    assert "| routed | 2/2 |" in report


def test_eval_stops_at_the_spending_ceiling(tmp_path: Path) -> None:
    cases = json.loads((EVAL_DIR / "cases.json").read_text())

    results = brain_eval.run_eval(cases, client=ScriptedClient(), max_usd=0.01, out_dir=tmp_path)

    assert len(results) < len(cases) * 2
