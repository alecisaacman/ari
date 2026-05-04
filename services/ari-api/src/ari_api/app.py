from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ari_core.core.paths import DB_PATH
from ari_core.modules.coordination.db import (
    ENTITY_CONFIG,
    get_coordination_entity,
    list_coordination_entities,
    put_coordination_entity,
)
from ari_core.modules.execution.coding_loop import (
    approve_stored_coding_loop_retry_approval,
    get_coding_loop_retry_approval,
    list_coding_loop_retry_approvals,
    reject_stored_coding_loop_retry_approval,
    run_one_step_coding_loop,
)
from ari_core.modules.execution.controller import (
    build_repo_context,
    plan_execution_goal,
    run_execution_goal,
)
from ari_core.modules.execution.engine import (
    approve_operator_action,
    create_operator_action,
    execute_command,
    get_execution_snapshot,
    get_operator_action,
    patch_file,
    read_file,
    run_operator_action,
    write_file,
)
from ari_core.modules.execution.inspection import (
    get_execution_plan_preview,
    get_execution_run,
    inspect_coding_loop_result,
    inspect_coding_loop_retry_approval,
    list_execution_plan_previews,
    list_execution_runs,
)
from ari_core.modules.execution.models import ExecutionGoal
from ari_core.modules.execution.tools import get_execution_tool_registry
from ari_core.modules.memory.capture import (
    capture_execution_run_memory,
    capture_recent_execution_run_memories,
)
from ari_core.modules.memory.context import build_memory_context
from ari_core.modules.memory.db import (
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
from ari_core.modules.memory.explain import explain_execution_run
from ari_core.modules.memory.self_model import ensure_self_model_memory, get_self_model_memory
from ari_core.modules.notes.db import save_ari_note, search_ari_notes
from ari_core.modules.policy.engine import (
    build_project_draft,
    classify_builder_output,
    derive_awareness,
    detect_capability_gaps,
    get_latest_awareness_snapshot,
    get_top_improvement_focus,
    store_awareness_snapshot,
    sync_project_focus,
)
from ari_core.modules.tasks.db import (
    create_ari_task,
    get_ari_task,
    list_ari_tasks,
    search_ari_tasks,
)
from fastapi import FastAPI, HTTPException, Query

from ari_api.schemas import (
    CodingActionCreateRequest,
    CodingLoopGoalRequest,
    CoordinationUpsertRequest,
    ExecutionCommandRequest,
    ExecutionGoalRequest,
    ExecutionPatchFileRequest,
    ExecutionReadFileRequest,
    ExecutionWriteFileRequest,
    MemoryBlockCreateRequest,
    MemoryCaptureExecutionRequest,
    MemoryCreateRequest,
    NoteCreateRequest,
    OrchestrationClassifyRequest,
    PolicyPayloadRequest,
    ProjectDraftRequest,
    RetryApprovalApproveRequest,
    RetryApprovalRejectRequest,
    TaskCreateRequest,
)

MEMORY_TYPES_QUERY = Query(default_factory=list)


def create_app() -> FastAPI:
    app = FastAPI(title="ARI API", version="0.1.0")

    def guard(operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return operation()
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "service": "ari-api",
            "dbPath": str(DB_PATH),
            "dbExists": Path(DB_PATH).exists(),
            "entities": sorted(ENTITY_CONFIG.keys()),
        }

    @app.post("/notes")
    def create_note(payload: NoteCreateRequest) -> dict[str, Any]:
        return _row_to_note(save_ari_note(payload.title, payload.content))

    @app.get("/notes")
    def list_notes(
        query: str = Query(default=""),
        limit: int = Query(default=20, ge=1, le=200),
    ) -> dict[str, Any]:
        return {
            "query": query,
            "notes": [_row_to_note(row) for row in search_ari_notes(query, limit=limit)],
        }

    @app.post("/tasks")
    def create_task(payload: TaskCreateRequest) -> dict[str, Any]:
        return _row_to_task(create_ari_task(payload.title, payload.notes))

    @app.get("/tasks")
    def list_tasks(
        query: str = Query(default=""),
        limit: int = Query(default=20, ge=1, le=200),
    ) -> dict[str, Any]:
        rows = (
            search_ari_tasks(query, limit=limit) if query.strip() else list_ari_tasks(limit=limit)
        )
        return {"query": query, "tasks": [_row_to_task(row) for row in rows]}

    @app.get("/tasks/{task_id}")
    def get_task(task_id: int) -> dict[str, Any]:
        task = get_ari_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
        return _row_to_task(task)

    @app.post("/memory")
    def create_memory(payload: MemoryCreateRequest) -> dict[str, Any]:
        return _row_to_memory(
            remember_ari_memory(
                payload.type,
                payload.title,
                payload.content,
                tags=payload.tags,
            )
        )

    @app.get("/memory")
    def list_memory(
        query: str = Query(default=""),
        types: list[str] = MEMORY_TYPES_QUERY,
        limit: int = Query(default=20, ge=1, le=200),
    ) -> dict[str, Any]:
        if query.strip():
            rows = search_ari_memories(query, limit=limit, memory_types=types)
        else:
            rows = list_ari_memories(memory_types=types, limit=limit)
        return {"query": query, "memories": [_row_to_memory(row) for row in rows]}

    @app.post("/memory/blocks")
    def create_memory_block_endpoint(payload: MemoryBlockCreateRequest) -> dict[str, Any]:
        return memory_block_to_payload(
            create_memory_block(
                layer=payload.layer,
                kind=payload.kind,
                title=payload.title,
                body=payload.body,
                source=payload.source,
                importance=payload.importance,
                confidence=payload.confidence,
                tags=payload.tags,
                subject_ids=payload.subjectIds,
                evidence=payload.evidence,
            )
        )

    @app.get("/memory/blocks")
    def list_memory_block_endpoint(
        layer: str | None = Query(default=None),
        query: str = Query(default=""),
        limit: int = Query(default=20, ge=1, le=200),
    ) -> dict[str, Any]:
        rows = (
            search_memory_blocks(query, layer=layer, limit=limit)
            if query.strip()
            else list_memory_blocks(layer=layer, limit=limit)
        )
        return {
            "query": query,
            "blocks": [memory_block_to_payload(row) for row in rows],
        }

    @app.get("/memory/blocks/{block_id}")
    def get_memory_block_endpoint(block_id: str) -> dict[str, Any]:
        block = get_memory_block(block_id)
        if block is None:
            raise HTTPException(status_code=404, detail=f"Memory block {block_id} not found.")
        return memory_block_to_payload(block)

    @app.get("/memory/context")
    def memory_context(
        query: str = Query(default=""),
        layers: list[str] = MEMORY_TYPES_QUERY,
        limit: int = Query(default=10, ge=1, le=50),
    ) -> dict[str, Any]:
        return build_memory_context(query, layers=layers, limit=limit)

    @app.post("/memory/capture/execution")
    def capture_execution_memory(payload: MemoryCaptureExecutionRequest) -> dict[str, Any]:
        if payload.runId:
            return {"block": capture_execution_run_memory(payload.runId)}
        return {"blocks": capture_recent_execution_run_memories(limit=payload.limit)}

    @app.get("/explain/execution/{run_id}")
    def explain_execution(run_id: str) -> dict[str, Any]:
        return explain_execution_run(run_id)

    @app.post("/memory/self-model/ensure")
    def ensure_self_model() -> dict[str, Any]:
        return {"blocks": ensure_self_model_memory()}

    @app.get("/memory/self-model")
    def get_self_model() -> dict[str, Any]:
        return {"blocks": get_self_model_memory()}

    @app.get("/memory/{memory_id}")
    def get_memory(memory_id: int) -> dict[str, Any]:
        record = get_ari_memory(memory_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found.")
        return _row_to_memory(record)

    @app.put("/coordination/{entity}")
    def put_coordination(entity: str, payload: CoordinationUpsertRequest) -> dict[str, Any]:
        _ensure_entity(entity)
        return _row_to_record(put_coordination_entity(entity, payload.payload))

    @app.get("/coordination/{entity}")
    def list_coordination(
        entity: str,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        _ensure_entity(entity)
        return {
            "records": [
                _row_to_record(row) for row in list_coordination_entities(entity, limit=limit)
            ]
        }

    @app.get("/coordination/{entity}/{record_id}")
    def get_coordination(entity: str, record_id: str) -> dict[str, Any]:
        _ensure_entity(entity)
        row = get_coordination_entity(entity, record_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"{entity} record {record_id} not found.")
        return _row_to_record(row)

    @app.get("/orchestration")
    def list_orchestration_records(
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        return list_coordination("orchestration_record", limit)

    @app.get("/orchestration/{record_id}")
    def get_orchestration_record(record_id: str) -> dict[str, Any]:
        return get_coordination("orchestration_record", record_id)

    @app.put("/orchestration")
    def put_orchestration_record(payload: CoordinationUpsertRequest) -> dict[str, Any]:
        return put_coordination("orchestration_record", payload)

    @app.post("/awareness/derive")
    def awareness_derive(payload: PolicyPayloadRequest) -> dict[str, Any]:
        return derive_awareness(payload.payload)

    @app.post("/awareness/store")
    def awareness_store(payload: PolicyPayloadRequest) -> dict[str, Any]:
        return store_awareness_snapshot(payload.payload)

    @app.get("/awareness/latest")
    def awareness_latest() -> dict[str, Any]:
        return {"snapshot": get_latest_awareness_snapshot()}

    @app.post("/policy/orchestration/classify")
    def policy_orchestration_classify(payload: OrchestrationClassifyRequest) -> dict[str, Any]:
        return classify_builder_output(
            payload.rawOutput,
            current_priority=payload.currentPriority,
            latest_decision=payload.latestDecision,
        )

    @app.post("/policy/improvements/detect")
    def policy_improvements_detect(payload: PolicyPayloadRequest) -> dict[str, Any]:
        return {"drafts": detect_capability_gaps(payload.payload)}

    @app.get("/policy/improvements/focus")
    def policy_improvements_focus() -> dict[str, Any]:
        return {"record": get_top_improvement_focus()}

    @app.post("/policy/projects/draft")
    def policy_projects_draft(payload: ProjectDraftRequest) -> dict[str, Any]:
        return build_project_draft(payload.model_dump())

    @app.get("/policy/projects/focus")
    def policy_projects_focus() -> dict[str, Any]:
        return {"focus": sync_project_focus()}

    @app.post("/execution/command")
    def execution_command(payload: ExecutionCommandRequest) -> dict[str, Any]:
        return guard(
            lambda: execute_command(
                payload.command,
                cwd=payload.cwd,
                timeout_seconds=payload.timeoutSeconds,
            )
        )

    @app.post("/execution/files/read")
    def execution_read_file(payload: ExecutionReadFileRequest) -> dict[str, Any]:
        return guard(lambda: read_file(payload.path))

    @app.post("/execution/files/write")
    def execution_write_file(payload: ExecutionWriteFileRequest) -> dict[str, Any]:
        return guard(
            lambda: write_file(
                payload.path,
                payload.content,
                action_id=payload.actionId,
            )
        )

    @app.post("/execution/files/patch")
    def execution_patch_file(payload: ExecutionPatchFileRequest) -> dict[str, Any]:
        return guard(
            lambda: patch_file(
                payload.path,
                find_text=payload.find,
                replace_text=payload.replace,
                action_id=payload.actionId,
            )
        )

    @app.post("/execution/goals")
    def execution_goal(payload: ExecutionGoalRequest) -> dict[str, Any]:
        return guard(
            lambda: run_execution_goal(
                ExecutionGoal(
                    objective=payload.goal,
                    max_cycles=payload.maxCycles,
                ),
                planner_mode=payload.planner,
            ).to_dict()
        )

    @app.post("/execution/plans")
    def execution_plan(payload: ExecutionGoalRequest) -> dict[str, Any]:
        return guard(
            lambda: plan_execution_goal(
                ExecutionGoal(
                    objective=payload.goal,
                    max_cycles=payload.maxCycles,
                ),
                planner_mode=payload.planner,
            )
        )

    @app.post("/execution/coding-loop")
    def execution_coding_loop(payload: CodingLoopGoalRequest) -> dict[str, Any]:
        return guard(
            lambda: {
                "coding_loop": inspect_coding_loop_result(
                    run_one_step_coding_loop(
                        payload.goal,
                        execution_root=payload.executionRoot,
                        planner_mode=payload.planner,
                    )
                )
            }
        )

    @app.get("/execution/coding-loop/retry-approvals")
    def execution_retry_approvals(
        limit: int = Query(default=10, ge=1, le=50),
    ) -> dict[str, Any]:
        return {
            "retry_approvals": [
                inspect_coding_loop_retry_approval(approval)
                for approval in list_coding_loop_retry_approvals(limit=limit)
            ]
        }

    @app.get("/execution/coding-loop/retry-approvals/{approval_id}")
    def execution_retry_approval(approval_id: str) -> dict[str, Any]:
        approval = get_coding_loop_retry_approval(approval_id)
        if approval is None:
            raise HTTPException(
                status_code=404,
                detail=f"Coding-loop retry approval {approval_id} not found.",
            )
        return {"retry_approval": inspect_coding_loop_retry_approval(approval)}

    @app.post("/execution/coding-loop/retry-approvals/{approval_id}/approve")
    def execution_approve_retry_approval(
        approval_id: str,
        payload: RetryApprovalApproveRequest,
    ) -> dict[str, Any]:
        return guard(
            lambda: {
                "retry_approval": inspect_coding_loop_retry_approval(
                    approve_stored_coding_loop_retry_approval(
                        approval_id,
                        approved_by=payload.approvedBy,
                    )
                )
            }
        )

    @app.post("/execution/coding-loop/retry-approvals/{approval_id}/reject")
    def execution_reject_retry_approval(
        approval_id: str,
        payload: RetryApprovalRejectRequest,
    ) -> dict[str, Any]:
        return guard(
            lambda: {
                "retry_approval": inspect_coding_loop_retry_approval(
                    reject_stored_coding_loop_retry_approval(
                        approval_id,
                        rejected_reason=payload.reason,
                        rejected_by=payload.rejectedBy,
                    )
                )
            }
        )

    @app.get("/execution/plans")
    def execution_plans(
        limit: int = Query(default=10, ge=1, le=50),
    ) -> dict[str, Any]:
        return {"plans": list_execution_plan_previews(limit=limit)}

    @app.get("/execution/plans/{preview_id}")
    def execution_plan_preview(preview_id: str) -> dict[str, Any]:
        preview = get_execution_plan_preview(preview_id)
        if preview is None:
            raise HTTPException(
                status_code=404,
                detail=f"Execution plan preview {preview_id} not found.",
            )
        return {"plan": preview}

    @app.get("/execution/tools")
    def execution_tools() -> dict[str, Any]:
        return get_execution_tool_registry().prompt_payload()

    @app.get("/execution/context")
    def execution_context(
        execution_root: str | None = Query(default=None, alias="executionRoot"),
    ) -> dict[str, Any]:
        return {"context": build_repo_context(execution_root).to_dict()}

    @app.get("/execution/runs")
    def execution_runs(
        limit: int = Query(default=10, ge=1, le=50),
    ) -> dict[str, Any]:
        return {"runs": list_execution_runs(limit=limit)}

    @app.get("/execution/runs/{run_id}")
    def execution_run(run_id: str) -> dict[str, Any]:
        run = get_execution_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Execution run {run_id} not found.")
        return {"run": run}

    @app.post("/execution/actions")
    def execution_create_action(payload: CodingActionCreateRequest) -> dict[str, Any]:
        return guard(
            lambda: {
                "action": create_operator_action(
                    title=payload.title,
                    summary=payload.summary,
                    operations=[
                        operation.model_dump(exclude_none=True) for operation in payload.operations
                    ],
                    verify_command=payload.verifyCommand,
                    working_directory=payload.workingDirectory,
                    approval_required=payload.approvalRequired,
                )
            }
        )

    @app.get("/execution/actions")
    def execution_list_actions(
        limit: int = Query(default=6, ge=1, le=50),
    ) -> dict[str, Any]:
        return {"actions": get_execution_snapshot(limit=limit)["recent_actions"]}

    @app.get("/execution/actions/{action_id}")
    def execution_get_action(action_id: str) -> dict[str, Any]:
        action = get_operator_action(action_id)
        if action is None:
            raise HTTPException(status_code=404, detail=f"Execution action {action_id} not found.")
        return {"action": action}

    @app.post("/execution/actions/{action_id}/approve")
    def execution_approve_action(action_id: str) -> dict[str, Any]:
        return guard(lambda: {"action": approve_operator_action(action_id)})

    @app.post("/execution/actions/{action_id}/run")
    def execution_run_action(action_id: str) -> dict[str, Any]:
        return guard(lambda: run_operator_action(action_id))

    @app.get("/execution/snapshot")
    def execution_snapshot(
        limit: int = Query(default=6, ge=1, le=50),
    ) -> dict[str, Any]:
        return get_execution_snapshot(limit=limit)

    return app


def _ensure_entity(entity: str) -> None:
    if entity not in ENTITY_CONFIG:
        raise HTTPException(status_code=404, detail=f"Unknown coordination entity: {entity}")


def _row_to_record(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _row_to_note(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "content": row["body"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_task(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "status": row["status"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_memory(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "type": row["type"],
        "title": row["title"],
        "content": row["content"],
        "tags": _json_array(row["tags_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _json_array(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(value) for value in raw]
    import json

    try:
        decoded = json.loads(raw)
    except Exception:
        return []
    if not isinstance(decoded, list):
        return []
    return [str(value) for value in decoded]
