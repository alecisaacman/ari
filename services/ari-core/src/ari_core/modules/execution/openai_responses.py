"""OpenAI Responses API adapter for ARI execution planning.

This module intentionally exposes a narrow completion function compatible with
ModelPlanner. It returns a strict JSON string and does not execute actions.
"""

from __future__ import annotations

import json
import os
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .command_policy import validate_command

DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"


OPENAI_PLANNER_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "confidence",
        "summary",
        "assumptions",
        "risks",
        "actions",
        "verification",
    ],
    "properties": {
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "summary": {"type": "string"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "path_or_command", "reason", "safety_notes"],
                "properties": {
                    "type": {"type": "string"},
                    "path_or_command": {"type": "string"},
                    "reason": {"type": "string"},
                    "safety_notes": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "verification": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "command"],
                "properties": {
                    "type": {"type": "string"},
                    "command": {"type": "string"},
                },
            },
        },
    },
}

FILE_ACTION_TYPES = {"read_file", "write_file", "patch_file", "propose_edit"}
COMMAND_ACTION_TYPES = {"run_command", "run_test"}
MUTATING_ACTION_TYPES = {"write_file", "patch_file"}


def build_openai_completion_fn(
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> Any:
    """Build a completion_fn(payload) callable for ModelPlanner.

    The returned callable sends ARI's planner payload to OpenAI and expects the
    model to return only strict JSON matching the WorkerPlan schema described in
    the payload.
    """
    resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for planner_mode=openai.")

    resolved_model = model or os.getenv("ARI_OPENAI_MODEL") or DEFAULT_OPENAI_MODEL

    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError(
            "The openai package is required for planner_mode=openai. "
            "Install it in the active environment before using this backend."
        ) from error

    client = OpenAI(api_key=resolved_api_key)

    def complete(payload: dict[str, object]) -> str:
        response = client.responses.create(
            model=resolved_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are ARI's constrained execution planner. "
                        "Return only strict JSON. Do not include markdown. "
                        "Do not execute actions. Do not invent files outside allowed_files."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "ari_planner_output",
                    "strict": True,
                    "schema": OPENAI_PLANNER_OUTPUT_SCHEMA,
                }
            },
        )

        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return validate_openai_planner_output(output_text, payload)

        raise RuntimeError("OpenAI Responses API returned no output_text.")

    return complete


def validate_openai_planner_output(raw_output: str, payload: Mapping[str, object]) -> str:
    """Validate strict OpenAI planner output and return ModelPlanner-compatible JSON."""

    raw = raw_output.strip()
    if raw.startswith("```") or "```" in raw:
        raise RuntimeError("OpenAI planner returned markdown instead of strict JSON.")

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"OpenAI planner returned invalid JSON: {error}") from error

    if not isinstance(decoded, dict):
        raise RuntimeError("OpenAI planner output must be a JSON object.")

    _require_fields(
        decoded,
        ("confidence", "summary", "assumptions", "risks", "actions", "verification"),
        "OpenAI planner output",
    )
    confidence = decoded["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        raise RuntimeError("OpenAI planner confidence must be numeric.")
    if confidence < 0 or confidence > 1:
        raise RuntimeError("OpenAI planner confidence must be between 0 and 1.")

    summary = _require_string(decoded["summary"], "OpenAI planner summary")
    assumptions = _require_string_list(decoded["assumptions"], "OpenAI planner assumptions")
    risks = _require_string_list(decoded["risks"], "OpenAI planner risks")
    raw_actions = _require_list(decoded["actions"], "OpenAI planner actions")
    raw_verification = _require_list(decoded["verification"], "OpenAI planner verification")

    max_actions = int(payload.get("max_plan_actions") or 5)
    if len(raw_actions) > max_actions:
        raise RuntimeError(f"OpenAI planner emitted more than {max_actions} actions.")

    allowed_actions = _allowed_strings(payload.get("allowed_actions"))
    allowed_files = _allowed_strings(payload.get("allowed_files"))
    allowed_commands = _allowed_strings(payload.get("allowed_commands"))
    repo_root = _repo_root_from_payload(payload)

    actions = [
        _validate_action(action, allowed_actions, allowed_files, allowed_commands, repo_root)
        for action in raw_actions
    ]
    verification = [
        _validate_verification(item, allowed_commands, repo_root) for item in raw_verification
    ]

    return json.dumps(
        {
            "confidence": confidence,
            "reason": summary,
            "summary": summary,
            "assumptions": assumptions,
            "risks": risks,
            "actions": actions,
            "verification": verification,
        },
        separators=(",", ":"),
    )


def _validate_action(
    raw_action: object,
    allowed_actions: set[str],
    allowed_files: set[str],
    allowed_commands: set[str],
    repo_root: Path | None,
) -> dict[str, object]:
    if not isinstance(raw_action, dict):
        raise RuntimeError("Each OpenAI planner action must be an object.")
    _require_fields(raw_action, ("type", "path_or_command", "reason", "safety_notes"), "action")
    action_type = _require_string(raw_action["type"], "action type")
    target = _require_string(raw_action["path_or_command"], "action path_or_command")
    reason = _require_string(raw_action["reason"], "action reason")
    safety_notes = _require_string_list(raw_action["safety_notes"], "action safety_notes")

    if allowed_actions and action_type not in allowed_actions:
        raise RuntimeError(f"OpenAI planner proposed disallowed action type: {action_type}")
    if action_type in MUTATING_ACTION_TYPES:
        raise RuntimeError(
            f"OpenAI strict planner schema does not support mutating action type: {action_type}"
        )
    if len(reason.strip()) < 8:
        raise RuntimeError("OpenAI planner action reason is too vague.")

    normalized: dict[str, object] = {
        "type": action_type,
        "path_or_command": target,
        "reason": reason,
        "safety_notes": safety_notes,
    }
    if action_type in FILE_ACTION_TYPES:
        if target not in allowed_files:
            raise RuntimeError(f"OpenAI planner invented file target: {target}")
        normalized["path"] = target
    elif action_type in COMMAND_ACTION_TYPES:
        if target not in allowed_commands:
            raise RuntimeError(f"OpenAI planner invented command target: {target}")
        policy_result = validate_command(target, repo_root=repo_root)
        if not policy_result.allowed:
            raise RuntimeError(
                "OpenAI planner command failed verification policy: "
                f"{policy_result.reason}"
            )
        normalized["command"] = shlex.split(target)
        if action_type == "run_test":
            normalized["type"] = "run_command"
    else:
        raise RuntimeError(f"OpenAI planner proposed unregistered action type: {action_type}")
    return normalized


def _validate_verification(
    raw_verification: object,
    allowed_commands: set[str],
    repo_root: Path | None,
) -> dict[str, object]:
    if not isinstance(raw_verification, dict):
        raise RuntimeError("Each OpenAI planner verification item must be an object.")
    _require_fields(raw_verification, ("type", "command"), "verification")
    verification_type = _require_string(raw_verification["type"], "verification type")
    command = _require_string(raw_verification["command"], "verification command")
    if command not in allowed_commands:
        raise RuntimeError(f"OpenAI planner invented verification command: {command}")
    policy_result = validate_command(command, repo_root=repo_root)
    if not policy_result.allowed:
        raise RuntimeError(
            "OpenAI planner verification command failed policy: "
            f"{policy_result.reason}"
        )
    return {
        "type": "action_success",
        "target": verification_type,
        "command": command,
        "reason": f"Planner requested verification command: {command}",
    }


def _require_fields(raw: Mapping[str, object], fields: tuple[str, ...], label: str) -> None:
    missing = [field for field in fields if field not in raw]
    if missing:
        raise RuntimeError(f"{label} missing required fields: {', '.join(missing)}")


def _require_string(raw: object, label: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise RuntimeError(f"{label} must be a non-empty string.")
    return raw.strip()


def _require_string_list(raw: object, label: str) -> list[str]:
    items = _require_list(raw, label)
    if not all(isinstance(item, str) for item in items):
        raise RuntimeError(f"{label} must contain only strings.")
    return [item.strip() for item in items]


def _require_list(raw: object, label: str) -> list[object]:
    if not isinstance(raw, list):
        raise RuntimeError(f"{label} must be a list.")
    return raw


def _allowed_strings(raw: object) -> set[str]:
    if not isinstance(raw, list):
        return set()
    return {item for item in raw if isinstance(item, str)}


def _repo_root_from_payload(payload: Mapping[str, object]) -> Path | None:
    repo_context = payload.get("repo_context")
    if not isinstance(repo_context, dict):
        return None
    repo_root = repo_context.get("repo_root")
    if not isinstance(repo_root, str) or not repo_root.strip():
        return None
    return Path(repo_root)
