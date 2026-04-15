import json
from pathlib import Path

from ...core.paths import DB_PATH
from .engine import (
    build_project_draft,
    classify_builder_output,
    derive_awareness,
    detect_capability_gaps,
    get_latest_awareness_snapshot,
    get_top_improvement_focus,
    store_awareness_snapshot,
    sync_project_focus,
)


def _parse_payload(args) -> dict:
    payload = json.loads(args.payload_json or "{}")
    if not isinstance(payload, dict):
        raise ValueError("payload_json must decode to an object")
    return payload


def handle_api_policy_awareness_derive(args, db_path: Path = DB_PATH) -> int:
    payload = _parse_payload(args)
    print(json.dumps(derive_awareness(payload, db_path=db_path)))
    return 0


def handle_api_policy_awareness_store(args, db_path: Path = DB_PATH) -> int:
    payload = _parse_payload(args)
    print(json.dumps(store_awareness_snapshot(payload, db_path=db_path)))
    return 0


def handle_api_policy_awareness_latest(args, db_path: Path = DB_PATH) -> int:
    snapshot = get_latest_awareness_snapshot(db_path=db_path)
    print(json.dumps({"snapshot": snapshot}))
    return 0


def handle_api_policy_orchestration_classify(args, db_path: Path = DB_PATH) -> int:
    payload = _parse_payload(args)
    print(
        json.dumps(
            classify_builder_output(
                payload.get("rawOutput", ""),
                current_priority=payload.get("currentPriority", ""),
                latest_decision=payload.get("latestDecision", ""),
            )
        )
    )
    return 0


def handle_api_policy_improvement_detect(args, db_path: Path = DB_PATH) -> int:
    payload = _parse_payload(args)
    print(json.dumps({"drafts": detect_capability_gaps(payload)}))
    return 0


def handle_api_policy_improvement_focus(args, db_path: Path = DB_PATH) -> int:
    print(json.dumps({"record": get_top_improvement_focus(db_path=db_path)}))
    return 0


def handle_api_policy_project_draft(args, db_path: Path = DB_PATH) -> int:
    payload = _parse_payload(args)
    print(json.dumps(build_project_draft(payload, db_path=db_path)))
    return 0


def handle_api_policy_project_focus(args, db_path: Path = DB_PATH) -> int:
    print(json.dumps({"focus": sync_project_focus(db_path=db_path)}))
    return 0

