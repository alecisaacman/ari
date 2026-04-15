import json
from pathlib import Path
from typing import Any, Dict

from ...core.paths import DB_PATH
from .db import get_coordination_entity, list_coordination_entities, put_coordination_entity


def _row_to_payload(row) -> Dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def handle_api_coordination_put(args, db_path: Path = DB_PATH) -> int:
    payload = json.loads(args.payload_json)
    if not isinstance(payload, dict):
        raise ValueError("payload_json must decode to an object")
    row = put_coordination_entity(args.entity, payload, db_path=db_path)
    print(json.dumps(_row_to_payload(row)))
    return 0


def handle_api_coordination_get(args, db_path: Path = DB_PATH) -> int:
    row = get_coordination_entity(args.entity, args.id, db_path=db_path)
    if row is None:
        print(json.dumps({"record": None}))
        return 0
    print(json.dumps(_row_to_payload(row)))
    return 0


def handle_api_coordination_list(args, db_path: Path = DB_PATH) -> int:
    rows = [_row_to_payload(row) for row in list_coordination_entities(args.entity, limit=args.limit, db_path=db_path)]
    print(json.dumps({"records": rows}))
    return 0
