from __future__ import annotations

import json

from ari_core.modules.execution.openai_responses import build_openai_completion_fn
from dotenv import load_dotenv

load_dotenv()

payload: dict[str, object] = {
    "goal": "Create a safe preview plan to inspect the ARI repo. Do not execute anything.",
    "allowed_actions": ["read_file"],
    "allowed_files": ["README.md"],
    "instructions": [
        "Return strict JSON only.",
        "Do not use markdown.",
        "Do not execute actions.",
        "Use only allowed_actions.",
        "Use only allowed_files.",
    ],
    "expected_shape": {
        "confidence": "number between 0 and 1",
        "actions": [
            {
                "type": "read_file",
                "path": "README.md",
            }
        ],
        "verification": [],
    },
}

complete = build_openai_completion_fn()
raw = complete(payload)

print("RAW MODEL OUTPUT:")
print(raw)

print("\nPARSED JSON:")
parsed = json.loads(raw)
print(json.dumps(parsed, indent=2))
