from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from ari_core.core.paths import DB_PATH
from ari_core.modules.memory.db import list_memory_blocks, memory_block_to_payload

LIFECYCLE_LESSON_KIND = "coding_loop_chain_lifecycle_summary"


@dataclass(frozen=True, slots=True)
class LifecycleLessonSummary:
    lesson_id: str
    source_type: str
    source_id: str | None
    related_coding_loop_result_id: str | None
    related_chain_id: str | None
    summary: str
    lesson_text: str
    confidence: float | None
    importance: int | None
    tags: tuple[str, ...]
    created_at: str | None
    updated_at: str | None
    inspection_hint: str
    availability_status: str
    unavailable_reason: str | None


@dataclass(frozen=True, slots=True)
class LifecycleLessonsReadModel:
    generated_at: str
    total_recent_count: int
    lessons: tuple[LifecycleLessonSummary, ...]
    unavailable_reason: str | None
    source_of_truth: str
    authority_warning: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_lifecycle_lessons_read_model(
    *,
    db_path: Path = DB_PATH,
    limit: int = 20,
) -> LifecycleLessonsReadModel:
    source_of_truth = "canonical memory blocks with coding-loop chain lifecycle summaries"
    authority_warning = (
        "This read model is inspection-only. ACE may display lifecycle lessons but "
        "must not create, edit, delete, mutate, or own ARI memory."
    )
    try:
        blocks = list_memory_blocks(layer="session", limit=limit, db_path=db_path)
    except Exception as error:  # pragma: no cover - exercised through tests via monkeypatch.
        return LifecycleLessonsReadModel(
            generated_at=_now_iso(),
            total_recent_count=0,
            lessons=(),
            unavailable_reason=(
                f"Lifecycle lessons are unavailable: {type(error).__name__}: {error}"
            ),
            source_of_truth=source_of_truth,
            authority_warning=authority_warning,
        )

    lessons = tuple(
        _summarize_lifecycle_block(memory_block_to_payload(block))
        for block in blocks
        if block["kind"] == LIFECYCLE_LESSON_KIND
    )
    return LifecycleLessonsReadModel(
        generated_at=_now_iso(),
        total_recent_count=len(lessons),
        lessons=lessons,
        unavailable_reason=None,
        source_of_truth=source_of_truth,
        authority_warning=authority_warning,
    )


def _summarize_lifecycle_block(payload: dict[str, object]) -> LifecycleLessonSummary:
    evidence = _first_evidence(payload)
    lesson_id = str(payload.get("id") or "")
    source_id = _string_or_none(payload.get("source"))
    related_result_id = _string_or_none(evidence.get("root_coding_loop_result_id")) or source_id
    return LifecycleLessonSummary(
        lesson_id=lesson_id,
        source_type=str(evidence.get("type") or payload.get("kind") or "memory_block"),
        source_id=source_id,
        related_coding_loop_result_id=related_result_id,
        related_chain_id=related_result_id,
        summary=str(payload.get("title") or ""),
        lesson_text=_lesson_text(payload, evidence),
        confidence=_float_or_none(payload.get("confidence")),
        importance=_int_or_none(payload.get("importance")),
        tags=tuple(str(tag) for tag in _list_value(payload.get("tags"))),
        created_at=_string_or_none(payload.get("created_at")),
        updated_at=_string_or_none(payload.get("updated_at")),
        inspection_hint=f"api memory blocks get --id {lesson_id}",
        availability_status="available",
        unavailable_reason=None,
    )


def _lesson_text(payload: dict[str, object], evidence: dict[str, object]) -> str:
    lesson = _string_or_none(evidence.get("lesson"))
    if lesson:
        return lesson
    body = str(payload.get("body") or "")
    for line in body.splitlines():
        if line.startswith("Lesson:"):
            return line.removeprefix("Lesson:").strip()
    return body


def _first_evidence(payload: dict[str, object]) -> dict[str, object]:
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        return {}
    for item in evidence:
        if isinstance(item, dict):
            return item
    return {}


def _list_value(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _float_or_none(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
