import sqlite3
from pathlib import Path
from typing import Any

from ...core.paths import DB_PATH
from ..networking.db import get_connection, initialize_database

ENTITY_CONFIG: dict[str, dict[str, Any]] = {
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
    "decision_record": {
        "table": "ari_decision_records",
        "primary_key": "id",
        "columns": [
            "id",
            "orchestration_run_id",
            "signal_id",
            "intent",
            "decision_type",
            "priority",
            "reasoning",
            "related_signal_ids_json",
            "related_entity_type",
            "related_entity_id",
            "proposed_action_json",
            "requires_approval",
            "action_json",
            "confidence",
            "created_at",
        ],
        "order_by": "created_at desc",
    },
    "decision_dispatch_record": {
        "table": "ari_decision_dispatch_records",
        "primary_key": "id",
        "columns": [
            "id",
            "decision_id",
            "decision_reference",
            "status",
            "reason",
            "action_json",
            "execution_result_json",
            "created_at",
        ],
        "order_by": "created_at desc",
    },
    "decision_evaluation_record": {
        "table": "ari_decision_evaluation_records",
        "primary_key": "id",
        "columns": [
            "id",
            "decision_id",
            "dispatch_record_id",
            "decision_reference",
            "status",
            "reason",
            "next_step",
            "created_at",
        ],
        "order_by": "created_at desc",
    },
    "decision_cycle_record": {
        "table": "ari_decision_cycle_records",
        "primary_key": "id",
        "columns": [
            "id",
            "orchestration_run_id",
            "status",
            "reason",
            "decision_count",
            "dispatch_count",
            "evaluation_count",
            "created_at",
        ],
        "order_by": "created_at desc",
    },
    "runtime_loop_record": {
        "table": "ari_runtime_loop_records",
        "primary_key": "id",
        "columns": [
            "id",
            "goal",
            "status",
            "reason",
            "cycles_run",
            "max_cycles",
            "final_output",
            "final_error",
            "last_worker_run_id",
            "created_at",
            "updated_at",
        ],
        "order_by": "updated_at desc",
    },
    "runtime_worker_run": {
        "table": "ari_runtime_worker_runs",
        "primary_key": "id",
        "columns": [
            "id",
            "loop_id",
            "cycle_index",
            "prompt",
            "backend",
            "command_json",
            "cwd",
            "success",
            "retryable",
            "exit_code",
            "stdout",
            "stderr",
            "created_at",
        ],
        "order_by": "created_at desc",
    },
    "runtime_controller_decision": {
        "table": "ari_runtime_controller_decisions",
        "primary_key": "id",
        "columns": [
            "id",
            "loop_id",
            "cycle_index",
            "goal",
            "selected_slice_key",
            "selected_slice_title",
            "selected_slice_milestone",
            "selection_reason",
            "evidence_json",
            "verification_plan_json",
            "outcome_status",
            "outcome_reason",
            "next_control_action",
            "created_at",
            "updated_at",
        ],
        "order_by": "updated_at desc",
    },
    "runtime_action_plan": {
        "table": "ari_runtime_action_plans",
        "primary_key": "id",
        "columns": [
            "id",
            "loop_id",
            "cycle_index",
            "slice_key",
            "milestone",
            "attempt_kind",
            "task_description",
            "constraints_json",
            "likely_files_json",
            "expected_symbols_json",
            "verification_expectations_json",
            "retry_refinement_hints_json",
            "failed_checks_json",
            "prompt_text",
            "created_at",
            "updated_at",
        ],
        "order_by": "updated_at desc",
    },
    "runtime_execution_run": {
        "table": "ari_runtime_execution_runs",
        "primary_key": "id",
        "columns": [
            "id",
            "goal_id",
            "objective",
            "status",
            "reason",
            "cycles_run",
            "max_cycles",
            "repo_root",
            "contexts_json",
            "decisions_json",
            "results_json",
            "created_at",
            "updated_at",
        ],
        "order_by": "updated_at desc",
    },
    "runtime_execution_plan_preview": {
        "table": "ari_runtime_execution_plan_previews",
        "primary_key": "id",
        "columns": [
            "id",
            "goal_id",
            "objective",
            "status",
            "reason",
            "repo_root",
            "context_json",
            "memory_context_json",
            "planner_config_json",
            "planner_result_json",
            "decision_json",
            "validation_error",
            "created_at",
        ],
        "order_by": "created_at desc",
    },
    "runtime_coding_loop_retry_approval": {
        "table": "ari_runtime_coding_loop_retry_approvals",
        "primary_key": "approval_id",
        "columns": [
            "approval_id",
            "source_coding_loop_result_id",
            "source_preview_id",
            "source_execution_run_id",
            "original_goal",
            "proposed_retry_goal",
            "proposed_retry_action_json",
            "proposed_retry_action_description",
            "reason",
            "failed_verification_summary",
            "approval_status",
            "approval_json",
            "retry_execution_requires_approval",
            "proposed_action_requires_approval",
            "retry_execution_run_id",
            "retry_execution_status",
            "retry_execution_reason",
            "created_at",
            "updated_at",
            "executed_at",
            "rejected_by",
            "rejected_at",
        ],
        "order_by": "coalesce(updated_at, created_at) desc",
    },
}


def _config_for(entity: str) -> dict[str, Any]:
    if entity not in ENTITY_CONFIG:
        raise ValueError(f"Unknown coordination entity: {entity}")
    return ENTITY_CONFIG[entity]


def put_coordination_entity(
    entity: str,
    payload: dict[str, Any],
    db_path: Path = DB_PATH,
) -> sqlite3.Row:
    config = _config_for(entity)
    initialize_database(db_path=db_path)
    columns: list[str] = config["columns"]
    primary_key = config["primary_key"]
    if primary_key not in payload:
        raise ValueError(f"Missing primary key for {entity}: {primary_key}")

    values = [payload.get(column) for column in columns]
    placeholders = ", ".join("?" for _ in columns)
    update_assignments = ", ".join(
        f"{column} = excluded.{column}" for column in columns if column != primary_key
    )

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


def get_coordination_entity(
    entity: str,
    identifier: str,
    db_path: Path = DB_PATH,
) -> sqlite3.Row | None:
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


def list_coordination_entities(
    entity: str,
    limit: int = 50,
    db_path: Path = DB_PATH,
) -> list[sqlite3.Row]:
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
