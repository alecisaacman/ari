import json
from pathlib import Path
from typing import List, Optional

from ...core.paths import DB_PATH
from .db import get_ari_memory, list_ari_memories, remember_ari_memory, search_ari_memories


def _parse_types(raw_types) -> List[str]:
    if not raw_types:
        return []
    return [value for value in raw_types if value]


def _parse_tags(raw_tags_json: Optional[str]) -> List[str]:
    if not raw_tags_json:
        return []
    parsed = json.loads(raw_tags_json)
    if not isinstance(parsed, list):
        raise ValueError("tags_json must decode to a list of strings")
    return [str(value) for value in parsed]


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
    memory = remember_ari_memory(args.type, args.title, args.body, tags=_parse_tags(args.tags_json), db_path=db_path)
    payload = _row_to_memory_payload(memory)
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f'Saved canonical ARI memory #{payload["id"]}: {payload["type"]} {payload["title"]}')
    return 0


def handle_api_memory_list(args, db_path: Path = DB_PATH) -> int:
    memories = [_row_to_memory_payload(row) for row in list_ari_memories(_parse_types(args.type), limit=args.limit, db_path=db_path)]
    payload = {"memories": memories}
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Loaded {len(memories)} canonical ARI memory record(s).")
    return 0


def handle_api_memory_search(args, db_path: Path = DB_PATH) -> int:
    memories = [
        _row_to_memory_payload(row)
        for row in search_ari_memories(args.query, limit=args.limit, memory_types=_parse_types(args.type), db_path=db_path)
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
        print(f'Canonical ARI memory #{args.id} was not found.')
        return 1

    payload = _row_to_memory_payload(memory)
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f'Loaded canonical ARI memory #{payload["id"]}: {payload["type"]} {payload["title"]}')
    return 0
