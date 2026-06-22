from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from ari_core.modules.memory.db import create_memory_block
from ari_core.modules.overview import get_ari_operating_overview, read_model


def test_ari_overview_is_json_serializable() -> None:
    overview = get_ari_operating_overview()

    payload = overview.to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)

    assert decoded["system_label"] == "ARI local-first operating overview"
    assert decoded["dashboard_mode"] == "read_only"
    assert decoded["generated_at"].endswith("Z")


def test_ari_overview_includes_skill_counts() -> None:
    overview = get_ari_operating_overview()

    assert overview.active_skill_count == 1
    assert overview.prototype_skill_count == 1
    assert overview.candidate_skill_count >= 8


def test_ari_overview_lists_active_prototype_and_candidate_skills() -> None:
    overview = get_ari_operating_overview()

    active_ids = {skill.skill_id for skill in overview.active_skills}
    prototype_ids = {skill.skill_id for skill in overview.prototype_skills}
    candidate_ids = {skill.skill_id for skill in overview.candidate_skills}

    assert "ari.native.coding_loop" in active_ids
    assert "ari.native.self_documentation" in prototype_ids
    assert "ari.native.file_organization" in candidate_ids
    assert "ari.native.document_processing" in candidate_ids


def test_ari_overview_authority_warning_keeps_ace_read_only() -> None:
    overview = get_ari_operating_overview()

    assert "ACE may display" in overview.authority_warning
    assert "must not approve" in overview.authority_warning
    assert "execute" in overview.authority_warning
    assert "own ARI state" in overview.authority_warning


def test_ari_overview_includes_live_summary_count_fields(tmp_path: Path) -> None:
    overview = get_ari_operating_overview(db_path=tmp_path / "ari.db")

    assert overview.pending_approval_count.value == 0
    assert overview.pending_approval_count.status == "live"
    assert overview.recent_coding_loop_count.value == 0
    assert overview.recent_lifecycle_lesson_count.value == 0
    assert overview.recent_memory_lesson_count.value == 0
    assert overview.counts_generated_from_live_sources is True
    assert overview.unavailable_counts == ()
    assert overview.partial_counts_reason is None


def test_ari_overview_counts_lifecycle_memory_lessons(tmp_path: Path) -> None:
    db_path = tmp_path / "ari.db"
    create_memory_block(
        block_id="memory-block-coding-loop-chain-proof",
        layer="session",
        kind="coding_loop_chain_lifecycle_summary",
        title="Coding-loop chain proof",
        body="Lesson: keep the retry boundary explicit.",
        source="coding-loop-result-proof",
        db_path=db_path,
    )
    create_memory_block(
        block_id="memory-block-other-proof",
        layer="session",
        kind="manual_note",
        title="Other note",
        body="Not a lifecycle lesson.",
        source="manual",
        db_path=db_path,
    )

    overview = get_ari_operating_overview(db_path=db_path)

    assert overview.recent_lifecycle_lesson_count.value == 1
    assert overview.recent_memory_lesson_count.value == 1
    assert overview.counts_generated_from_live_sources is True


def test_ari_overview_represents_unavailable_counts_honestly(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_list_memory_blocks(*args, **kwargs):
        raise RuntimeError("memory unavailable")

    monkeypatch.setattr(read_model, "list_memory_blocks", fail_list_memory_blocks)

    overview = get_ari_operating_overview(db_path=tmp_path / "ari.db")

    assert overview.pending_approval_count.status == "live"
    assert overview.recent_coding_loop_count.status == "live"
    assert overview.recent_lifecycle_lesson_count.value is None
    assert overview.recent_lifecycle_lesson_count.status == "partial_unavailable"
    assert "recent_lifecycle_lesson_count" in overview.unavailable_counts
    assert overview.counts_generated_from_live_sources is False
    assert overview.partial_counts_reason is not None


def test_ari_overview_does_not_execute_skills(monkeypatch) -> None:
    def fail_external(*args, **kwargs):
        raise AssertionError(f"unexpected execution call: {args} {kwargs}")

    monkeypatch.setattr("subprocess.run", fail_external)

    overview = get_ari_operating_overview()

    assert overview.active_skill_count == 1


def test_ari_overview_does_not_call_external_services(monkeypatch) -> None:
    def fail_urlopen(*args, **kwargs):
        raise AssertionError(f"unexpected external call: {args} {kwargs}")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    overview = get_ari_operating_overview()

    assert overview.dashboard_mode == "read_only"
