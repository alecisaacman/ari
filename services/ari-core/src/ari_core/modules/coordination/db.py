import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.paths import DB_PATH
from ..networking.db import get_connection, initialize_database


ENTITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "project": {
        "table": "ari_projects",
        "primary_key": "id",
        "columns": [
            "id",
            "title",
            "goal",
            "completion_criteria",
            "status",
            "source",
            "created_at",
            "updated_at",
        ],
        "order_by": "updated_at desc",
    },
    "project_milestone": {
        "table": "ari_project_milestones",
        "primary_key": "id",
        "columns": [
            "id",
            "project_id",
            "title",
            "status",
            "completion_criteria",
            "sequence",
            "created_at",
            "updated_at",
        ],
        "order_by": "sequence asc, updated_at desc",
    },
    "project_step": {
        "table": "ari_project_steps",
        "primary_key": "id",
        "columns": [
            "id",
            "project_id",
            "milestone_id",
            "title",
            "status",
            "completion_criteria",
            "depends_on_step_ids_json",
            "blocked_by_json",
            "sequence",
            "linked_task_id",
            "linked_improvement_id",
            "created_at",
            "updated_at",
        ],
        "order_by": "sequence asc, updated_at desc",
    },
    "orchestration_record": {
        "table": "ari_orchestration_records",
        "primary_key": "id",
        "columns": [
            "id",
            "source",
            "raw_output",
            "status",
            "classification",
            "concise_summary",
            "next_instruction",
            "reasoning",
            "escalation_required",
            "escalation_packet_json",
            "alec_decision",
            "parent_orchestration_id",
            "linked_improvement_ids_json",
            "verification_signal",
            "linkage_mode",
            "created_at",
            "processed_at",
        ],
        "order_by": "created_at desc",
    },
    "self_improvement": {
        "table": "ari_self_improvements",
        "primary_key": "id",
        "columns": [
            "id",
            "capability",
            "missing_capability",
            "why_it_matters",
            "what_it_unlocks",
            "smallest_slice",
            "next_best_action",
            "approval_required",
            "relative_priority",
            "leverage_score",
            "urgency_score",
            "dependency_value_score",
            "autonomy_impact_score",
            "implementation_effort_score",
            "priority_score",
            "status",
            "dedupe_key",
            "approval_id",
            "task_id",
            "instruction_orchestration_id",
            "dispatch_record_id",
            "dispatch_orchestration_id",
            "dispatch_mode",
            "dispatch_evidence",
            "consumed_at",
            "consumer",
            "completion_orchestration_id",
            "completion_evidence",
            "verification_orchestration_id",
            "verification_evidence",
            "reflection_json",
            "first_observed_at",
            "last_observed_at",
            "approved_at",
            "queued_at",
            "dispatched_at",
            "completed_at",
            "verified_at",
        ],
        "order_by": "priority_score desc, last_observed_at desc",
    },
    "dispatch_record": {
        "table": "ari_builder_dispatch_records",
        "primary_key": "id",
        "columns": [
            "id",
            "orchestration_id",
            "linked_improvement_ids_json",
            "mode",
            "instruction",
            "summary",
            "reasoning",
            "routing_state",
            "dispatch_status",
            "trigger",
            "dispatched_at",
            "consumed_at",
            "consumer",
            "completion_orchestration_id",
            "verification_orchestration_id",
            "created_at",
            "updated_at",
        ],
        "order_by": "updated_at desc",
    },
    "execution_outcome": {
        "table": "ari_execution_outcomes",
        "primary_key": "item_key",
        "columns": [
            "item_key",
            "item_type",
            "item_id",
            "title",
            "state",
            "stage",
            "state_since",
            "last_progress_at",
            "completed_at",
            "blocked_reason",
            "failure_reason",
            "verification_signal",
            "next_action",
            "evidence_mode",
            "metadata_json",
            "updated_at",
        ],
        "order_by": "updated_at desc",
    },
}


def _config_for(entity: str) -> Dict[str, Any]:
    if entity not in ENTITY_CONFIG:
        raise ValueError(f"Unknown coordination entity: {entity}")
    return ENTITY_CONFIG[entity]


def put_coordination_entity(entity: str, payload: Dict[str, Any], db_path: Path = DB_PATH) -> sqlite3.Row:
    config = _config_for(entity)
    initialize_database(db_path=db_path)
    columns: List[str] = config["columns"]
    primary_key = config["primary_key"]
    if primary_key not in payload:
        raise ValueError(f"Missing primary key for {entity}: {primary_key}")

    values = [payload.get(column) for column in columns]
    placeholders = ", ".join("?" for _ in columns)
    update_assignments = ", ".join(f"{column} = excluded.{column}" for column in columns if column != primary_key)

    with get_connection(db_path) as connection:
        connection.execute(
            f"""
            insert into {config["table"]} ({", ".join(columns)})
            values ({placeholders})
            on conflict({primary_key}) do update set
            {update_assignments}
            """,
            tuple(values),
        )
        connection.commit()
        row = connection.execute(
            f"""
            select {", ".join(columns)}
            from {config["table"]}
            where {primary_key} = ?
            """,
            (payload[primary_key],),
        ).fetchone()
    assert row is not None
    return row


def get_coordination_entity(entity: str, identifier: str, db_path: Path = DB_PATH) -> Optional[sqlite3.Row]:
    if not db_path.exists():
        return None

    config = _config_for(entity)
    try:
        with get_connection(db_path) as connection:
            row = connection.execute(
                f"""
                select {", ".join(config["columns"])}
                from {config["table"]}
                where {config["primary_key"]} = ?
                """,
                (identifier,),
            ).fetchone()
        return row
    except sqlite3.OperationalError as error:
        if f"no such table: {config['table']}" in str(error):
            return None
        raise


def list_coordination_entities(entity: str, limit: int = 50, db_path: Path = DB_PATH) -> List[sqlite3.Row]:
    if not db_path.exists():
        return []

    config = _config_for(entity)
    try:
        with get_connection(db_path) as connection:
            rows = connection.execute(
                f"""
                select {", ".join(config["columns"])}
                from {config["table"]}
                order by {config["order_by"]}
                limit ?
                """,
                (limit,),
            ).fetchall()
        return list(rows)
    except sqlite3.OperationalError as error:
        if f"no such table: {config['table']}" in str(error):
            return []
        raise

