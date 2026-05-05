from __future__ import annotations

import json
from pathlib import Path

from ...core.paths import DB_PATH
from .capture import (
    capture_coding_loop_retry_approval_memory,
    capture_execution_run_memory,
    capture_recent_execution_run_memories,
)
from .context import build_memory_context
from .db import (
    create_memory_block,
    get_ari_memory,
    get_memory_block,
    list_ari_memories,
    list_memory_blocks,
    memory_block_to_payload,
    remember_ari_memory,
    search_ari_memories,
    search_memory_blocks,
)
from .explain import explain_coding_loop_retry_approval, explain_execution_run
from .self_model import ensure_self_model_memory, get_self_model_memory


def _parse_types(raw_types: list[str] | None) -> list[str]:
    if not raw_types:
        return []
    return [value for value in raw_types if value]


def _parse_tags(raw_tags_json: str | None) -> list[str]:
    if not raw_tags_json:
        return []
    parsed = json.loads(raw_tags_json)
    if not isinstance(parsed, list):
        raise ValueError("tags_json must decode to a list of strings")
    return [str(value) for value in parsed]


def _parse_json_list(raw_json: str | None, *, field_name: str) -> list[object]:
    if not raw_json:
        return []
    parsed = json.loads(raw_json)
    if not isinstance(parsed, list):
        raise ValueError(f"{field_name} must decode to a list")
    return parsed


def _row_to_memory_payload(row) -> dict:
    return {
        "id": str(row["id"]),
        "type": row["type"],
        "title": row["title"],
        "content": row["content"],
        "tags": json.loads(row["tags_json"] or "[]"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def handle_api_memory_remember(args, db_path: Path = DB_PATH) -> int:
    memory = remember_ari_memory(
        args.type,
        args.title,
        args.body,
        tags=_parse_tags(args.tags_json),
        db_path=db_path,
    )
    payload = _row_to_memory_payload(memory)
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Saved canonical ARI memory #{payload['id']}: {payload['type']} {payload['title']}")
    return 0


def handle_api_memory_list(args, db_path: Path = DB_PATH) -> int:
    memories = [
        _row_to_memory_payload(row)
        for row in list_ari_memories(
            _parse_types(args.type),
            limit=args.limit,
            db_path=db_path,
        )
    ]
    payload = {"memories": memories}
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Loaded {len(memories)} canonical ARI memory record(s).")
    return 0


def handle_api_memory_search(args, db_path: Path = DB_PATH) -> int:
    memories = [
        _row_to_memory_payload(row)
        for row in search_ari_memories(
            args.query,
            limit=args.limit,
            memory_types=_parse_types(args.type),
            db_path=db_path,
        )
    ]
    payload = {"query": args.query, "memories": memories}
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Found {len(memories)} canonical ARI memory record(s).")
    return 0


def handle_api_memory_get(args, db_path: Path = DB_PATH) -> int:
    memory = get_ari_memory(int(args.id), db_path=db_path)
    if memory is None:
        payload = {"memory": None}
        if getattr(args, "as_json", False):
            print(json.dumps(payload))
            return 0
        print(f"Canonical ARI memory #{args.id} was not found.")
        return 1

    payload = _row_to_memory_payload(memory)
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Loaded canonical ARI memory #{payload['id']}: {payload['type']} {payload['title']}")
    return 0


def handle_api_memory_block_create(args, db_path: Path = DB_PATH) -> int:
    evidence = _parse_json_list(args.evidence_json, field_name="evidence_json")
    if not all(isinstance(item, dict) for item in evidence):
        raise ValueError("evidence_json must decode to a list of objects")
    block = create_memory_block(
        layer=args.layer,
        kind=args.kind,
        title=args.title,
        body=args.body,
        source=args.source,
        importance=args.importance,
        confidence=args.confidence,
        tags=[str(item) for item in _parse_json_list(args.tags_json, field_name="tags_json")],
        subject_ids=[
            str(item)
            for item in _parse_json_list(args.subject_ids_json, field_name="subject_ids_json")
        ],
        evidence=evidence,
        db_path=db_path,
    )
    payload = memory_block_to_payload(block)
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Saved ARI memory block {payload['id']}: {payload['layer']} {payload['title']}")
    return 0


def handle_api_memory_block_list(args, db_path: Path = DB_PATH) -> int:
    blocks = [
        memory_block_to_payload(row)
        for row in list_memory_blocks(layer=args.layer, limit=args.limit, db_path=db_path)
    ]
    payload = {"blocks": blocks}
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Loaded {len(blocks)} ARI memory block(s).")
    return 0


def handle_api_memory_block_search(args, db_path: Path = DB_PATH) -> int:
    blocks = [
        memory_block_to_payload(row)
        for row in search_memory_blocks(
            args.query,
            layer=args.layer,
            limit=args.limit,
            db_path=db_path,
        )
    ]
    payload = {"query": args.query, "blocks": blocks}
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Found {len(blocks)} ARI memory block(s).")
    return 0


def handle_api_memory_block_get(args, db_path: Path = DB_PATH) -> int:
    block = get_memory_block(args.id, db_path=db_path)
    if block is None:
        payload = {"block": None}
        if getattr(args, "as_json", False):
            print(json.dumps(payload))
            return 0
        print(f"ARI memory block {args.id} was not found.")
        return 1

    payload = memory_block_to_payload(block)
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Loaded ARI memory block {payload['id']}: {payload['layer']} {payload['title']}")
    return 0


def handle_api_memory_capture_execution(args, db_path: Path = DB_PATH) -> int:
    if args.id:
        payload: dict[str, object] = {
            "block": capture_execution_run_memory(args.id, db_path=db_path)
        }
    else:
        payload = {
            "blocks": capture_recent_execution_run_memories(
                limit=args.limit,
                db_path=db_path,
            )
        }
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        count = len(payload.get("blocks", [])) if "blocks" in payload else 1
        print(f"Captured {count} execution memory block(s).")
    return 0


def handle_api_memory_capture_retry_approval(args, db_path: Path = DB_PATH) -> int:
    payload = {
        "block": capture_coding_loop_retry_approval_memory(args.id, db_path=db_path)
    }
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Captured coding-loop retry approval memory block for {args.id}.")
    return 0


def handle_api_memory_explain_execution(args, db_path: Path = DB_PATH) -> int:
    payload = explain_execution_run(args.id, db_path=db_path)
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(payload["summary"])
    return 0


def handle_api_memory_explain_retry_approval(args, db_path: Path = DB_PATH) -> int:
    payload = explain_coding_loop_retry_approval(args.id, db_path=db_path)
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(payload["summary"])
    return 0


def handle_api_memory_context(args, db_path: Path = DB_PATH) -> int:
    payload = build_memory_context(
        args.query,
        layers=args.layer,
        limit=args.limit,
        db_path=db_path,
    )
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(payload["summary"])
    return 0


def handle_api_memory_self_model_ensure(args, db_path: Path = DB_PATH) -> int:
    blocks = ensure_self_model_memory(db_path=db_path)
    payload = {"blocks": blocks}
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Ensured {len(blocks)} ARI self-model memory block(s).")
    return 0


def handle_api_memory_self_model_show(args, db_path: Path = DB_PATH) -> int:
    blocks = get_self_model_memory(db_path=db_path)
    payload = {"blocks": blocks}
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Loaded {len(blocks)} ARI self-model memory block(s).")
    return 0
