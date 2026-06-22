from __future__ import annotations

import json

from ari_core.modules.self_documentation import (
    ContentIdea,
    generate_recording_plan_from_idea,
)


def test_recording_plan_is_json_serializable() -> None:
    plan = generate_recording_plan_from_idea(_idea())

    decoded = json.loads(json.dumps(plan.to_dict()))

    assert decoded["plan_id"].startswith("recording-plan-")
    assert decoded["source_idea_id"] == "content-idea-recording-test"


def test_recording_plan_includes_core_manual_recording_fields() -> None:
    plan = generate_recording_plan_from_idea(_idea()).to_dict()

    assert plan["hook"] == "This is what an AI interface looks like without becoming the brain."
    assert plan["narration_script"]
    assert plan["visual_layout"]
    assert plan["shot_list"]
    assert plan["suggested_raw_filename"].endswith("-raw.mov")
    assert plan["suggested_export_filename"].endswith("-final.mp4")
    assert plan["recording_format"] == "both"
    assert plan["estimated_duration_seconds"] == 60


def test_recording_plan_preserves_claims_and_redaction_notes() -> None:
    idea = _idea(
        redaction_notes=("Review private repo path before recording.",),
        claims_to_avoid=("Do not claim ACE owns decisions.",),
    )

    plan = generate_recording_plan_from_idea(idea).to_dict()

    assert plan["redaction_notes"] == ("Review private repo path before recording.",)
    assert plan["claims_to_avoid"] == ("Do not claim ACE owns decisions.",)


def test_recording_plan_suggests_dashboard_panels_and_terminal_commands() -> None:
    plan = generate_recording_plan_from_idea(_idea()).to_dict()

    assert "Content ideas" in plan["dashboard_panels_to_show"]
    assert "Self-documentation artifacts" in plan["dashboard_panels_to_show"]
    assert "Overview" in plan["dashboard_panels_to_show"]
    assert "api self-doc ideas list --json" in plan["terminal_commands_to_show"]
    assert "api overview content-ideas --json" in plan["terminal_commands_to_show"]
    assert "api overview show --json" in plan["terminal_commands_to_show"]


def test_recording_plan_does_not_generate_media_or_call_external_services(monkeypatch) -> None:
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(f"unexpected external call: {args} {kwargs}")
        ),
    )

    plan = generate_recording_plan_from_idea(_idea()).to_dict()

    assert "must not record, edit" in plan["approval_warning"]
    assert "upload" in plan["approval_warning"]
    assert "publish" in plan["approval_warning"]


def test_recording_plan_does_not_mutate_content_idea() -> None:
    idea = _idea()
    before = idea.to_dict()

    generate_recording_plan_from_idea(idea)

    assert idea.to_dict() == before


def _idea(
    *,
    redaction_notes: tuple[str, ...] = ("No sensitive-looking input was detected.",),
    claims_to_avoid: tuple[str, ...] = (
        "Do not claim ARI records or publishes content automatically.",
    ),
) -> ContentIdea:
    return ContentIdea(
        idea_id="content-idea-recording-test",
        title="Show ACE as a read-only window into ARI",
        hook="This is what an AI interface looks like without becoming the brain.",
        platform_fit=("LinkedIn", "TikTok/Reel"),
        audience="product-minded AI builders and operators",
        source_artifact_ids=("content-package-recording", "content-seed-recording"),
        source_artifact_types=("content_package", "content_seed"),
        proof_points=(
            "Commit 7be906c: Show content ideas in ACE",
            "ACE displays ARI-owned content ideas without controls.",
        ),
        visual_plan="Show ACE displaying ARI-owned read models and content ideas.",
        suggested_shot_list=(
            "Open the ACE dashboard.",
            "Show the Content Ideas panel and disabled controls.",
        ),
        script_angle="Show the dashboard reading ARI state without controls.",
        recording_difficulty="low",
        edit_complexity="low",
        risk_level="low",
        redaction_notes=redaction_notes,
        claims_to_avoid=claims_to_avoid,
        recommended_priority=88,
        reason_for_priority="Strong proof, low risk, and easy recording.",
        created_at="2026-05-07T00:00:00Z",
    )
