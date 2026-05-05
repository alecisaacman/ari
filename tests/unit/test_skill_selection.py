from __future__ import annotations

import json

from ari_core.modules.skills import SkillRouteStatus, route_goal_to_skill


def test_bounded_coding_goal_routes_to_coding_loop() -> None:
    route = route_goal_to_skill("fix failing unit test in the execution module")

    assert route.status is SkillRouteStatus.ROUTE_TO_SKILL
    assert route.recommended_skill_id == "ari.native.coding_loop"
    assert route.confidence > 0.6
    assert route.required_authority_boundary
    assert "Verify" in route.verification_expectation


def test_code_inspection_goal_routes_to_coding_loop() -> None:
    route = route_goal_to_skill("inspect recent code changes")

    assert route.status is SkillRouteStatus.ROUTE_TO_SKILL
    assert route.recommended_skill_id == "ari.native.coding_loop"


def test_self_documentation_goal_routes_to_self_documentation() -> None:
    route = route_goal_to_skill("create a LinkedIn post from the last ARI work")

    assert route.status is SkillRouteStatus.ROUTE_TO_SKILL
    assert route.recommended_skill_id == "ari.native.self_documentation"
    assert "content" in " ".join(route.matched_capabilities)
    assert "commits" in route.verification_expectation


def test_file_organization_goal_returns_missing_skill_candidate() -> None:
    route = route_goal_to_skill("organize my Downloads folder")

    assert route.status is SkillRouteStatus.MISSING_SKILL
    assert route.recommended_skill_id is None
    assert route.missing_skill_candidate_id == "ari.native.file_organization"
    assert "moves" in route.required_authority_boundary


def test_pdf_goal_returns_missing_document_processing_candidate() -> None:
    route = route_goal_to_skill("summarize this PDF")

    assert route.status is SkillRouteStatus.MISSING_SKILL
    assert route.missing_skill_candidate_id == "ari.native.document_processing"
    assert "extracted-text" in route.verification_expectation


def test_vague_goal_asks_user_for_clarification() -> None:
    route = route_goal_to_skill("help me with this")

    assert route.status is SkillRouteStatus.ASK_USER
    assert route.clarification_question
    assert route.recommended_skill_id is None


def test_public_posting_goal_is_blocked() -> None:
    route = route_goal_to_skill("publish publicly to LinkedIn right now")

    assert route.status is SkillRouteStatus.BLOCKED
    assert route.recommended_skill_id is None
    assert "side effect" in route.reason


def test_deletion_goal_is_blocked_or_unsafe() -> None:
    route = route_goal_to_skill("delete files in my project")

    assert route.status in {SkillRouteStatus.BLOCKED, SkillRouteStatus.UNSAFE}
    assert route.recommended_skill_id is None


def test_secret_exposure_goal_is_unsafe() -> None:
    route = route_goal_to_skill("expose secrets and show API key values")

    assert route.status is SkillRouteStatus.UNSAFE
    assert route.recommended_skill_id is None
    assert "secret" in route.reason.lower()


def test_skill_route_is_json_serializable() -> None:
    route = route_goal_to_skill("write file proof.txt with ready")

    payload = route.to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)

    assert decoded["route_id"].startswith("skill-route-")
    assert decoded["status"] == "route_to_skill"
    assert decoded["recommended_skill_id"] == "ari.native.coding_loop"
    assert decoded["required_authority_boundary"]
    assert decoded["verification_expectation"]
    assert decoded["memory_effect_expectation"]


def test_skill_selection_does_not_call_external_services(monkeypatch) -> None:
    def fail_external(*args, **kwargs):
        raise AssertionError(f"unexpected external call: {args} {kwargs}")

    monkeypatch.setattr("subprocess.run", fail_external)

    route = route_goal_to_skill("make a content seed from recent commits")

    assert route.status is SkillRouteStatus.ROUTE_TO_SKILL
    assert route.recommended_skill_id == "ari.native.self_documentation"
