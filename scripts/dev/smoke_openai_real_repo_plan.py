from __future__ import annotations

import json

from ari_core.modules.execution.openai_responses import build_openai_completion_fn
from dotenv import load_dotenv

load_dotenv()

candidate_files = [
    "services/ari-core/src/ari_core/modules/execution/openai_responses.py",
    "services/ari-core/src/ari_core/modules/execution/planners.py",
    "tests/unit/test_execution_controller.py",
    "scripts/dev/smoke_openai_planner.py",
]

ruff_command = (
    ".venv312/bin/python -m ruff check "
    "services/ari-core/src/ari_core/modules/execution/openai_responses.py "
    "services/ari-core/src/ari_core/modules/execution/planners.py"
)

payload: dict[str, object] = {
    "goal": (
        "Create a preview-only implementation plan to upgrade ARI's OpenAI planner "
        "adapter from loose json_object output to strict schema-constrained planner output. "
        "Do not execute anything. Do not edit files."
    ),
    "allowed_actions": ["read_file", "propose_edit", "run_test"],
    "allowed_files": candidate_files,
    "allowed_commands": [
        ".venv312/bin/python -m pytest tests/unit/test_execution_controller.py -q",
        ".venv312/bin/python -m pytest tests/unit -q",
        ruff_command,
    ],
    "required_output_shape": {
        "confidence": "number between 0 and 1",
        "summary": "string",
        "assumptions": ["string"],
        "risks": ["string"],
        "actions": [
            {
                "type": "one of: read_file, propose_edit, run_test",
                "path_or_command": "must be from allowed_files or allowed_commands",
                "reason": "string",
                "safety_notes": ["string"],
            }
        ],
        "verification": [
            {
                "type": "run_test",
                "command": "must be from allowed_commands",
            }
        ],
    },
    "constraints": [
        "Return strict JSON only.",
        "Do not use markdown.",
        "Do not execute actions.",
        "Do not invent files.",
        "Use only allowed_files.",
        "Use only allowed_commands.",
        "This is a preview plan only.",
    ],
}

complete = build_openai_completion_fn()
raw = complete(payload)

print("RAW MODEL OUTPUT:")
print(raw)

print("\nPARSED JSON:")
parsed = json.loads(raw)
print(json.dumps(parsed, indent=2))

# Basic local sanity checks.
allowed_files = set(candidate_files)
allowed_commands = set(payload["allowed_commands"])

for action in parsed.get("actions", []):
    target = action.get("path_or_command") or action.get("path") or action.get("command")
    if target and target not in allowed_files and target not in allowed_commands:
        raise SystemExit(f"Unsafe invented target: {target}")

print("\nSanity check passed: no invented action targets detected.")
