from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from ari_core.modules.execution import plan_execution_goal, resolve_execution_planner
from ari_core.modules.execution.openai_responses import (
    build_openai_completion_fn,
    validate_openai_planner_output,
)


def _payload() -> dict[str, object]:
    return {
        "allowed_actions": ["read_file", "run_command"],
        "allowed_files": ["README.md"],
        "allowed_commands": ["pytest"],
        "max_plan_actions": 5,
    }


def _strict_output(**overrides: object) -> str:
    output: dict[str, object] = {
        "confidence": 0.91,
        "summary": "Read the README to inspect the repo safely.",
        "assumptions": ["README.md exists in the provided repo context."],
        "risks": ["No mutation is required for this preview."],
        "actions": [
            {
                "type": "read_file",
                "path_or_command": "README.md",
                "reason": "Inspect the provided README file before proposing changes.",
                "safety_notes": ["Uses an allowed file target."],
            }
        ],
        "verification": [],
    }
    output.update(overrides)
    return json.dumps(output)


def test_openai_strict_output_normalizes_to_model_planner_json() -> None:
    normalized = json.loads(validate_openai_planner_output(_strict_output(), _payload()))

    assert normalized["confidence"] == 0.91
    assert normalized["reason"] == "Read the README to inspect the repo safely."
    assert normalized["actions"][0]["type"] == "read_file"
    assert normalized["actions"][0]["path"] == "README.md"


def test_openai_strict_output_rejects_invalid_json() -> None:
    with pytest.raises(RuntimeError, match="invalid JSON"):
        validate_openai_planner_output("{not-json", _payload())


def test_openai_strict_output_rejects_missing_required_fields() -> None:
    decoded = json.loads(_strict_output())
    decoded.pop("actions")
    with pytest.raises(RuntimeError, match="missing required fields"):
        validate_openai_planner_output(json.dumps(decoded), _payload())


def test_openai_strict_output_rejects_confidence_outside_range() -> None:
    with pytest.raises(RuntimeError, match="between 0 and 1"):
        validate_openai_planner_output(_strict_output(confidence=1.4), _payload())


def test_openai_strict_output_rejects_invented_file_target() -> None:
    raw = _strict_output(
        actions=[
            {
                "type": "read_file",
                "path_or_command": "invented.md",
                "reason": "Inspect a file that is not in the allowed file list.",
                "safety_notes": ["This should fail closed."],
            }
        ]
    )

    with pytest.raises(RuntimeError, match="invented file target"):
        validate_openai_planner_output(raw, _payload())


def test_openai_strict_output_rejects_invented_command_target() -> None:
    raw = _strict_output(
        actions=[
            {
                "type": "run_command",
                "path_or_command": "rm -rf .",
                "reason": "Run a command outside the allowlist.",
                "safety_notes": ["This should fail closed."],
            }
        ]
    )

    with pytest.raises(RuntimeError, match="invented command target"):
        validate_openai_planner_output(raw, _payload())


def test_openai_planner_missing_api_key_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    planner, selection = resolve_execution_planner(planner_mode="openai")

    assert planner.planner_name == "rule_based"
    assert selection.requested == "openai"
    assert selection.selected == "rule_based"
    assert selection.fallback_reason is not None


def test_openai_completion_uses_strict_json_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeResponses:
        def create(self, **kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            return SimpleNamespace(output_text=_strict_output())

    class FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key
            self.responses = FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    complete = build_openai_completion_fn(api_key="test-key", model="test-model")
    normalized = json.loads(complete(_payload()))

    assert normalized["actions"][0]["path"] == "README.md"
    assert calls[0]["text"]["format"]["type"] == "json_schema"
    assert calls[0]["text"]["format"]["strict"] is True


def test_openai_planning_preview_does_not_execute_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    readme = root / "README.md"
    readme.write_text("original\n", encoding="utf-8")

    class FakeResponses:
        def create(self, **kwargs: object) -> SimpleNamespace:
            del kwargs
            return SimpleNamespace(output_text=_strict_output())

    class FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key
            self.responses = FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    preview = plan_execution_goal(
        "Inspect README without mutation",
        execution_root=root,
        db_path=tmp_path / "state" / "networking.db",
        planner_mode="openai",
    )

    assert preview["status"] == "planned"
    assert preview["planner_config"]["requested"] == "openai"
    assert readme.read_text(encoding="utf-8") == "original\n"
