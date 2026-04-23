from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...core.paths import DB_PATH
from ..coordination.db import put_coordination_entity
from ..networking.db import get_connection, initialize_database


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def create_coding_action(
    payload: dict[str, Any],
    db_path: Path = DB_PATH,
) -> sqlite3.Row:
    initialize_database(db_path=db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            insert into ari_coding_actions (
                id,
                title,
                summary,
                status,
                approval_required,
                risky,
                target_paths_json,
                operations_json,
                verify_command,
                working_directory,
                current_step,
                last_command_run_id,
                last_command_summary,
                result_summary,
                retryable,
                blocked_reason,
                created_at,
                approved_at,
                applied_at,
                tested_at,
                passed_at,
                failed_at,
                verified_at,
                updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["title"],
                payload["summary"],
                payload["status"],
                int(payload["approval_required"]),
                int(payload["risky"]),
                payload["target_paths_json"],
                payload["operations_json"],
                payload["verify_command"],
                payload["working_directory"],
                payload["current_step"],
                payload.get("last_command_run_id"),
                payload.get("last_command_summary", ""),
                payload.get("result_summary", ""),
                int(payload.get("retryable", False)),
                payload.get("blocked_reason"),
                payload["created_at"],
                payload.get("approved_at"),
                payload.get("applied_at"),
                payload.get("tested_at"),
                payload.get("passed_at"),
                payload.get("failed_at"),
                payload.get("verified_at"),
                payload["updated_at"],
            ),
        )
        connection.commit()
        row = connection.execute(
            "select * from ari_coding_actions where id = ?",
            (payload["id"],),
        ).fetchone()
    assert row is not None
    return row


def update_coding_action(
    action_id: str,
    changes: dict[str, Any],
    db_path: Path = DB_PATH,
) -> sqlite3.Row:
    initialize_database(db_path=db_path)
    columns = ", ".join(f"{column} = ?" for column in changes)
    values = list(changes.values()) + [action_id]
    with get_connection(db_path) as connection:
        connection.execute(f"update ari_coding_actions set {columns} where id = ?", values)
        connection.commit()
        row = connection.execute(
            "select * from ari_coding_actions where id = ?",
            (action_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"Unknown coding action: {action_id}")
    return row


def get_coding_action(action_id: str, db_path: Path = DB_PATH) -> sqlite3.Row | None:
    if not db_path.exists():
        return None
    with get_connection(db_path) as connection:
        return connection.execute(
            "select * from ari_coding_actions where id = ?",
            (action_id,),
        ).fetchone()


def list_coding_actions(limit: int = 10, db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            select *
            from ari_coding_actions
            order by updated_at desc, created_at desc
            limit ?
            """,
            (limit,),
        ).fetchall()
    return list(rows)


def create_command_run(payload: dict[str, Any], db_path: Path = DB_PATH) -> sqlite3.Row:
    initialize_database(db_path=db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            insert into ari_command_runs (
                id,
                action_id,
                command,
                cwd,
                success,
                exit_code,
                timed_out,
                retryable,
                stdout,
                stderr,
                classification_json,
                created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["action_id"],
                payload["command"],
                payload["cwd"],
                int(payload["success"]),
                payload["exit_code"],
                int(payload["timed_out"]),
                int(payload["retryable"]),
                payload["stdout"],
                payload["stderr"],
                payload["classification_json"],
                payload["created_at"],
            ),
        )
        connection.commit()
        row = connection.execute(
            "select * from ari_command_runs where id = ?",
            (payload["id"],),
        ).fetchone()
    assert row is not None
    return row


def get_command_run(command_run_id: str, db_path: Path = DB_PATH) -> sqlite3.Row | None:
    if not db_path.exists():
        return None
    with get_connection(db_path) as connection:
        return connection.execute(
            "select * from ari_command_runs where id = ?",
            (command_run_id,),
        ).fetchone()


def list_command_runs(limit: int = 10, db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            select *
            from ari_command_runs
            order by created_at desc
            limit ?
            """,
            (limit,),
        ).fetchall()
    return list(rows)


def create_file_mutation(payload: dict[str, Any], db_path: Path = DB_PATH) -> sqlite3.Row:
    initialize_database(db_path=db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            insert into ari_file_mutations (
                id,
                action_id,
                path,
                operation,
                success,
                details,
                previous_sha256,
                new_sha256,
                created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload.get("action_id"),
                payload["path"],
                payload["operation"],
                int(payload["success"]),
                payload["details"],
                payload.get("previous_sha256"),
                payload.get("new_sha256"),
                payload["created_at"],
            ),
        )
        connection.commit()
        row = connection.execute(
            "select * from ari_file_mutations where id = ?",
            (payload["id"],),
        ).fetchone()
    assert row is not None
    return row


def list_file_mutations(limit: int = 10, db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            select *
            from ari_file_mutations
            order by created_at desc
            limit ?
            """,
            (limit,),
        ).fetchall()
    return list(rows)


def _upsert_execution_outcome(payload: dict[str, Any], db_path: Path = DB_PATH) -> None:
    put_coordination_entity("execution_outcome", payload, db_path=db_path)


def sync_action_execution_outcome(
    action_id: str,
    *,
    title: str,
    state: str,
    stage: str,
    state_since: str,
    next_action: str,
    blocked_reason: str | None = None,
    failure_reason: str | None = None,
    verification_signal: str | None = None,
    evidence_mode: str = "explicit",
    metadata: dict[str, Any] | None = None,
    completed_at: str | None = None,
    db_path: Path = DB_PATH,
) -> None:
    _upsert_execution_outcome(
        {
            "item_key": f"coding_action:{action_id}",
            "item_type": "coding_action",
            "item_id": action_id,
            "title": title,
            "state": state,
            "stage": stage,
            "state_since": state_since,
            "last_progress_at": state_since,
            "completed_at": completed_at,
            "blocked_reason": blocked_reason,
            "failure_reason": failure_reason,
            "verification_signal": verification_signal,
            "next_action": next_action,
            "evidence_mode": evidence_mode,
            "metadata_json": json.dumps(metadata or {}),
            "updated_at": now_iso(),
        },
        db_path=db_path,
    )


def row_to_coding_action_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "summary": row["summary"],
        "status": row["status"],
        "approval_required": bool(row["approval_required"]),
        "risky": bool(row["risky"]),
        "target_paths": _decode_json_list(row["target_paths_json"]),
        "operations": _decode_json_list(row["operations_json"]),
        "verify_command": row["verify_command"],
        "working_directory": row["working_directory"],
        "current_step": row["current_step"],
        "last_command_run_id": row["last_command_run_id"],
        "last_command_summary": row["last_command_summary"],
        "result_summary": row["result_summary"],
        "retryable": bool(row["retryable"]),
        "blocked_reason": row["blocked_reason"],
        "created_at": row["created_at"],
        "approved_at": row["approved_at"],
        "applied_at": row["applied_at"],
        "tested_at": row["tested_at"],
        "passed_at": row["passed_at"],
        "failed_at": row["failed_at"],
        "verified_at": row["verified_at"],
        "updated_at": row["updated_at"],
    }


def row_to_command_run_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "action_id": row["action_id"],
        "command": row["command"],
        "cwd": row["cwd"],
        "success": bool(row["success"]),
        "exit_code": row["exit_code"],
        "timed_out": bool(row["timed_out"]),
        "retryable": bool(row["retryable"]),
        "stdout": row["stdout"],
        "stderr": row["stderr"],
        "classification": json.loads(row["classification_json"] or "{}"),
        "created_at": row["created_at"],
    }


def row_to_file_mutation_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "action_id": row["action_id"],
        "path": row["path"],
        "operation": row["operation"],
        "success": bool(row["success"]),
        "details": row["details"],
        "previous_sha256": row["previous_sha256"],
        "new_sha256": row["new_sha256"],
        "created_at": row["created_at"],
    }


def _decode_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return decoded
