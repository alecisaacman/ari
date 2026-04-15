from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from ari_api.schemas import (
    CoordinationUpsertRequest,
    MemoryCreateRequest,
    NoteCreateRequest,
    OrchestrationClassifyRequest,
    PolicyPayloadRequest,
    ProjectDraftRequest,
    TaskCreateRequest,
)
from ari_core.core.paths import DB_PATH
from ari_core.modules.coordination.db import (
    ENTITY_CONFIG,
    get_coordination_entity,
    list_coordination_entities,
    put_coordination_entity,
)
from ari_core.modules.memory.db import (
    get_ari_memory,
    list_ari_memories,
    remember_ari_memory,
    search_ari_memories,
)
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
from ari_core.modules.tasks.db import create_ari_task, get_ari_task, list_ari_tasks, search_ari_tasks


def create_app() -> FastAPI:
    app = FastAPI(title="ARI API", version="0.1.0")

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
        rows = search_ari_tasks(query, limit=limit) if query.strip() else list_ari_tasks(limit=limit)
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
        types: list[str] = Query(default=[]),
        limit: int = Query(default=20, ge=1, le=200),
    ) -> dict[str, Any]:
        if query.strip():
            rows = search_ari_memories(query, limit=limit, memory_types=types)
        else:
            rows = list_ari_memories(memory_types=types, limit=limit)
        return {"query": query, "memories": [_row_to_memory(row) for row in rows]}

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
            "records": [_row_to_record(row) for row in list_coordination_entities(entity, limit=limit)]
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
