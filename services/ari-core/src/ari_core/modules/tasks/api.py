import json
from pathlib import Path

from ...core.paths import DB_PATH
from .db import create_ari_task, get_ari_task, list_ari_tasks, search_ari_tasks


def _row_to_task_payload(row) -> dict:
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "status": row["status"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def handle_api_tasks_create(args, db_path: Path = DB_PATH) -> int:
    task = create_ari_task(args.title, args.notes or "", db_path=db_path)
    payload = _row_to_task_payload(task)
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f'Saved canonical ARI task #{payload["id"]}: {payload["title"]}')
    return 0


def handle_api_tasks_list(args, db_path: Path = DB_PATH) -> int:
    tasks = [_row_to_task_payload(row) for row in list_ari_tasks(limit=args.limit, db_path=db_path)]
    payload = {"tasks": tasks}
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Loaded {len(tasks)} canonical ARI task(s).")
    return 0


def handle_api_tasks_get(args, db_path: Path = DB_PATH) -> int:
    task = get_ari_task(int(args.id), db_path=db_path)
    if task is None:
        payload = {"task": None}
        if getattr(args, "as_json", False):
            print(json.dumps(payload))
            return 0
        print(f'Canonical ARI task #{args.id} was not found.')
        return 1

    payload = _row_to_task_payload(task)
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f'Loaded canonical ARI task #{payload["id"]}: {payload["title"]}')
    return 0


def handle_api_tasks_search(args, db_path: Path = DB_PATH) -> int:
    tasks = [_row_to_task_payload(row) for row in search_ari_tasks(args.query, limit=args.limit, db_path=db_path)]
    payload = {"query": args.query, "tasks": tasks}
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f"Found {len(tasks)} canonical ARI task(s).")
    return 0
