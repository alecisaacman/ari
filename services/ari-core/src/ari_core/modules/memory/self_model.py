from __future__ import annotations

from pathlib import Path

from ...core.paths import DB_PATH
from .db import create_memory_block, list_memory_blocks, memory_block_to_payload

SELF_MODEL_BLOCKS = (
    {
        "block_id": "memory-block-self-model-core-authority",
        "kind": "core_identity",
        "title": "ARI is the single brain",
        "body": (
            "ARI owns decision-making, memory, execution, state, orchestration, "
            "signals, alerts, and explainability. ACE is an interface layer and "
            "must not become a second source of intelligence."
        ),
        "tags": ["self-model", "architecture", "authority"],
        "subject_ids": ["ARI", "ACE"],
    },
    {
        "block_id": "memory-block-self-model-local-first",
        "kind": "operating_boundary",
        "title": "ARI is local-first and inspectable",
        "body": (
            "ARI must preserve local-first operation, persistent state, typed data, "
            "traceable actions, and inspectable memory before expanding external "
            "or ambient capabilities."
        ),
        "tags": ["self-model", "local-first", "traceability"],
        "subject_ids": ["ARI"],
    },
    {
        "block_id": "memory-block-self-model-fail-closed",
        "kind": "safety_behavior",
        "title": "ARI fails closed on unsafe execution",
        "body": (
            "ARI validates planner output, file targets, commands, action bounds, "
            "and verification results before acting. Invalid or unsafe plans are "
            "rejected with visible reasons."
        ),
        "tags": ["self-model", "execution", "safety"],
        "subject_ids": ["ARI", "execution-core"],
    },
)


def ensure_self_model_memory(*, db_path: Path = DB_PATH) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for definition in SELF_MODEL_BLOCKS:
        row = create_memory_block(
            block_id=str(definition["block_id"]),
            replace_existing=True,
            layer="self_model",
            kind=str(definition["kind"]),
            title=str(definition["title"]),
            body=str(definition["body"]),
            source="ari_operating_directive",
            importance=5,
            confidence=1.0,
            tags=definition["tags"],
            subject_ids=definition["subject_ids"],
            evidence=[
                {
                    "type": "operating_directive",
                    "id": str(definition["block_id"]),
                    "source": "AGENTS.md and ARI build doctrine",
                }
            ],
            db_path=db_path,
        )
        blocks.append(memory_block_to_payload(row))
    return blocks


def get_self_model_memory(*, db_path: Path = DB_PATH) -> list[dict[str, object]]:
    return [
        memory_block_to_payload(row)
        for row in list_memory_blocks(layer="self_model", limit=50, db_path=db_path)
    ]
