from __future__ import annotations

import importlib
import json
from pathlib import Path

from ari_core.modules.memory.db import create_memory_block


def test_lifecycle_lessons_read_model_is_json_serializable(tmp_path: Path) -> None:
    db_path = tmp_path / "ari.db"
    _create_lesson(db_path)

    module = _lessons_module()
    model = module.get_lifecycle_lessons_read_model(db_path=db_path)

    payload = model.to_dict()
    assert payload["total_recent_count"] == 1
    assert json.loads(json.dumps(payload))["lessons"][0]["lesson_id"] == (
        "memory-block-coding-loop-chain-result-1"
    )


def test_lifecycle_lessons_read_model_includes_lesson_summaries(tmp_path: Path) -> None:
    db_path = tmp_path / "ari.db"
    _create_lesson(db_path)
    create_memory_block(
        layer="session",
        kind="unrelated",
        title="Ignore me",
        body="Not a lifecycle lesson.",
        source="other",
        db_path=db_path,
    )

    payload = _lessons_module().get_lifecycle_lessons_read_model(db_path=db_path).to_dict()

    assert payload["total_recent_count"] == 1
    lesson = payload["lessons"][0]
    assert lesson["lesson_id"] == "memory-block-coding-loop-chain-result-1"
    assert lesson["source_type"] == "coding_loop_chain_lifecycle"
    assert lesson["source_id"] == "coding-loop-result-1"
    assert lesson["related_coding_loop_result_id"] == "coding-loop-result-1"
    assert lesson["related_chain_id"] == "coding-loop-result-1"
    assert lesson["summary"] == "Coding-loop chain stopped/1: Fix proof"
    assert lesson["lesson_text"] == "A bounded retry resolved the chain."
    assert lesson["confidence"] == 0.95
    assert lesson["importance"] == 4
    assert "chain-lifecycle" in lesson["tags"]
    assert lesson["inspection_hint"] == (
        "api memory blocks get --id memory-block-coding-loop-chain-result-1"
    )
    assert lesson["availability_status"] == "available"
    assert lesson["unavailable_reason"] is None


def test_lifecycle_lessons_read_model_represents_unavailable_source(monkeypatch) -> None:
    module = _lessons_module()

    def raise_unavailable(*, layer, limit, db_path):
        raise RuntimeError("memory store offline")

    monkeypatch.setattr(module, "list_memory_blocks", raise_unavailable)

    payload = module.get_lifecycle_lessons_read_model().to_dict()

    assert payload["total_recent_count"] == 0
    assert payload["lessons"] == ()
    assert "RuntimeError: memory store offline" in payload["unavailable_reason"]
    assert payload["source_of_truth"] == (
        "canonical memory blocks with coding-loop chain lifecycle summaries"
    )


def test_lifecycle_lessons_read_model_is_read_only(monkeypatch) -> None:
    module = _lessons_module()
    calls: list[str] = []

    def list_only(*, layer, limit, db_path):
        calls.append(f"{layer}:{limit}")
        return []

    monkeypatch.setattr(module, "list_memory_blocks", list_only)

    payload = module.get_lifecycle_lessons_read_model(limit=7).to_dict()

    assert calls == ["session:7"]
    assert "inspection-only" in payload["authority_warning"]
    assert "must not create, edit, delete, mutate" in payload["authority_warning"]


def _lessons_module():
    return importlib.import_module("ari_core.modules.overview.lifecycle_lessons")


def _create_lesson(db_path: Path) -> None:
    create_memory_block(
        block_id="memory-block-coding-loop-chain-result-1",
        layer="session",
        kind="coding_loop_chain_lifecycle_summary",
        title="Coding-loop chain stopped/1: Fix proof",
        body="\n".join(
            [
                "Original goal: Fix proof",
                "Terminal status: stopped",
                "Lesson: A bounded retry resolved the chain.",
            ]
        ),
        source="coding-loop-result-1",
        importance=4,
        confidence=0.95,
        tags=["execution", "coding-loop", "chain-lifecycle", "status:stopped"],
        subject_ids=["coding-loop-result-1"],
        evidence=[
            {
                "type": "coding_loop_chain_lifecycle",
                "root_coding_loop_result_id": "coding-loop-result-1",
                "lesson": "A bounded retry resolved the chain.",
            }
        ],
        db_path=db_path,
    )
