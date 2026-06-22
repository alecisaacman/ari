from __future__ import annotations

import importlib
import json

from ari_core.modules.skills import SkillReadinessStatus, evaluate_skill_readiness


def test_coding_loop_readiness_is_active() -> None:
    report = evaluate_skill_readiness("ari.native.coding_loop")

    assert report.status is SkillReadinessStatus.ACTIVE
    assert report.lifecycle_status == "active"
    assert report.can_route_goals_now is True
    assert report.can_execute_now is True
    assert report.can_promote_now is False
    assert "manifest_exists" in report.satisfied_gates
    assert "implementation_exists" in report.satisfied_gates
    assert report.required_authority_boundary
    assert report.required_verification


def test_self_documentation_readiness_is_prototype() -> None:
    report = evaluate_skill_readiness("ari.native.self_documentation")

    assert report.status is SkillReadinessStatus.PROTOTYPE
    assert report.lifecycle_status == "prototype"
    assert report.can_route_goals_now is True
    assert report.can_execute_now is False
    assert report.can_promote_now is False
    assert report.required_memory_effect
    assert report.required_inspection_surface


def test_file_organization_readiness_is_candidate_not_ready() -> None:
    report = evaluate_skill_readiness("ari.native.file_organization")

    assert report.status is SkillReadinessStatus.CANDIDATE_NOT_READY
    assert report.can_route_goals_now is False
    assert report.can_execute_now is False
    assert "implementation_exists" in report.missing_gates
    assert "tests_defined" in report.missing_gates
    assert report.required_authority_boundary


def test_document_processing_readiness_is_candidate_not_ready() -> None:
    report = evaluate_skill_readiness("ari.native.document_processing")

    assert report.status is SkillReadinessStatus.CANDIDATE_NOT_READY
    assert report.required_verification
    assert "validation_rules_defined" in report.missing_gates


def test_unknown_skill_readiness_fails_safely() -> None:
    report = evaluate_skill_readiness("ari.native.nope")

    assert report.status is SkillReadinessStatus.UNKNOWN_SKILL
    assert report.can_route_goals_now is False
    assert report.can_execute_now is False
    assert report.can_promote_now is False
    assert "manifest_exists" in report.missing_gates
    assert report.satisfied_gates == ()


def test_readiness_report_is_json_serializable() -> None:
    report = evaluate_skill_readiness("ari.native.coding_loop")

    payload = report.to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)

    assert decoded["readiness_id"].startswith("skill-readiness-")
    assert decoded["status"] == "active"
    assert decoded["skill_id"] == "ari.native.coding_loop"
    assert decoded["required_authority_boundary"]
    assert decoded["required_verification"]
    assert decoded["required_memory_effect"]
    assert decoded["required_inspection_surface"]
    assert decoded["satisfied_gates"]


def test_readiness_evaluator_does_not_execute_skills(monkeypatch) -> None:
    def fail_external(*args, **kwargs):
        raise AssertionError(f"unexpected execution call: {args} {kwargs}")

    monkeypatch.setattr("subprocess.run", fail_external)

    report = evaluate_skill_readiness("ari.native.coding_loop")

    assert report.status is SkillReadinessStatus.ACTIVE


def test_readiness_evaluator_does_not_dynamic_load_skills(monkeypatch) -> None:
    def fail_import_module(*args, **kwargs):
        raise AssertionError(f"unexpected dynamic import: {args} {kwargs}")

    monkeypatch.setattr(importlib, "import_module", fail_import_module)

    report = evaluate_skill_readiness("ari.native.self_documentation")

    assert report.status is SkillReadinessStatus.PROTOTYPE
