from __future__ import annotations

import importlib
import json

from ari_core.modules.skills import propose_missing_skill


def test_file_organization_goal_proposes_read_only_candidate() -> None:
    proposal = propose_missing_skill(goal="organize my Downloads folder")

    assert proposal.candidate_skill_id == "ari.native.file_organization"
    assert "Read-only local file scan" in proposal.proposed_first_slice
    assert "Do not move" in proposal.proposed_first_slice_scope
    assert any("No moving" in non_goal for non_goal in proposal.explicit_non_goals)


def test_document_goal_proposes_document_processing_candidate() -> None:
    proposal = propose_missing_skill(goal="summarize this PDF")

    assert proposal.candidate_skill_id == "ari.native.document_processing"
    assert "document extraction" in proposal.proposed_first_slice.lower()
    assert any("No external upload" in non_goal for non_goal in proposal.explicit_non_goals)


def test_research_goal_proposes_research_gathering_candidate() -> None:
    proposal = propose_missing_skill(goal="research companies for remote jobs")

    assert proposal.candidate_skill_id == "ari.native.research_gathering"
    assert "research plan" in proposal.proposed_first_slice.lower()
    assert any("No outreach" in non_goal for non_goal in proposal.explicit_non_goals)


def test_email_send_goal_proposes_read_only_triage_not_sending() -> None:
    proposal = propose_missing_skill(goal="send emails from my inbox")

    assert proposal.candidate_skill_id == "ari.native.email_calendar_triage"
    assert "Read-only" in proposal.proposed_first_slice
    assert "Do not send" in proposal.proposed_first_slice_scope
    assert any("No sending emails" in non_goal for non_goal in proposal.explicit_non_goals)


def test_proposal_includes_missing_gates_and_first_slice() -> None:
    proposal = propose_missing_skill(skill_id="ari.native.file_organization")

    assert "implementation_exists" in proposal.missing_gates
    assert "tests_defined" in proposal.missing_gates
    assert proposal.proposed_first_slice
    assert proposal.proposed_first_slice_scope


def test_proposal_includes_authority_and_verification_requirements() -> None:
    proposal = propose_missing_skill(goal="summarize this PDF")

    assert proposal.authority_boundary
    assert proposal.approval_requirements
    assert proposal.validation_requirements
    assert proposal.verification_requirements
    assert proposal.memory_effects
    assert proposal.user_approval_required_before_building is True


def test_unknown_broad_goal_fails_safely_with_clarification_proposal() -> None:
    proposal = propose_missing_skill(goal="make my life better")

    assert proposal.candidate_skill_id is None
    assert proposal.current_readiness_status == "ask_user"
    assert "clarify" in proposal.proposed_first_slice.lower()
    assert proposal.user_approval_required_before_building is True


def test_unknown_skill_id_fails_safely() -> None:
    proposal = propose_missing_skill(skill_id="ari.native.nope")

    assert proposal.candidate_skill_id is None
    assert proposal.current_readiness_status == "unknown_skill"
    assert "No safe candidate skill" in proposal.reason_skill_is_needed


def test_missing_skill_proposal_is_json_serializable() -> None:
    proposal = propose_missing_skill(goal="organize my Downloads folder")

    payload = proposal.to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)

    assert decoded["proposal_id"].startswith("missing-skill-proposal-")
    assert decoded["candidate_skill_id"] == "ari.native.file_organization"
    assert decoded["user_approval_required_before_building"] is True


def test_missing_skill_proposal_does_not_execute_skills(monkeypatch) -> None:
    def fail_external(*args, **kwargs):
        raise AssertionError(f"unexpected execution call: {args} {kwargs}")

    monkeypatch.setattr("subprocess.run", fail_external)

    proposal = propose_missing_skill(goal="research companies for remote jobs")

    assert proposal.candidate_skill_id == "ari.native.research_gathering"


def test_missing_skill_proposal_does_not_dynamic_load_skills(monkeypatch) -> None:
    def fail_import_module(*args, **kwargs):
        raise AssertionError(f"unexpected dynamic import: {args} {kwargs}")

    monkeypatch.setattr(importlib, "import_module", fail_import_module)

    proposal = propose_missing_skill(goal="summarize this PDF")

    assert proposal.candidate_skill_id == "ari.native.document_processing"
