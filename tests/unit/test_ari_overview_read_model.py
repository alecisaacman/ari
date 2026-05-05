from __future__ import annotations

import json
import urllib.request

from ari_core.modules.overview import get_ari_operating_overview


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


def test_ari_overview_represents_partial_sections_honestly() -> None:
    overview = get_ari_operating_overview()

    assert overview.pending_approval_count.value is None
    assert overview.pending_approval_count.status == "partial_unavailable"
    assert "not wired" in overview.pending_approval_count.reason
    assert overview.recent_coding_loop_count.value is None
    assert overview.recent_memory_lesson_count.value is None
    assert any("intentionally marked partial" in note for note in overview.read_model_notes)


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
