import json
from pathlib import Path

from ...core.paths import DB_PATH
from .db import save_ari_note, search_ari_notes


def _row_to_note_payload(row) -> dict:
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "content": row["body"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def handle_api_notes_save(args, db_path: Path = DB_PATH) -> int:
    note = save_ari_note(args.title, args.body, db_path=db_path)
    payload = _row_to_note_payload(note)
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        print(f'Saved canonical ARI note #{payload["id"]}: {payload["title"]}')
    return 0


def handle_api_notes_search(args, db_path: Path = DB_PATH) -> int:
    notes = [_row_to_note_payload(row) for row in search_ari_notes(args.query, limit=args.limit, db_path=db_path)]
    payload = {
        "query": args.query,
        "notes": notes,
    }
    if getattr(args, "as_json", False):
        print(json.dumps(payload))
    else:
        if notes:
            print(f"Found {len(notes)} canonical ARI note(s).")
        else:
            print("No canonical ARI notes found.")
    return 0
