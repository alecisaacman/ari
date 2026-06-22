from __future__ import annotations

import importlib
import json

from ari_core.modules.self_documentation import ContentIdea, ContentIdeaBank


def test_content_ideas_read_model_is_json_serializable(monkeypatch) -> None:
    module = _read_model_module()
    monkeypatch.setattr(module, "generate_content_idea_bank", _idea_bank)

    payload = module.get_content_ideas_read_model().to_dict()

    decoded = json.loads(json.dumps(payload))
    assert decoded["total_idea_count"] == 1
    assert decoded["recent_ideas"][0]["idea_id"] == "content-idea-read-model"


def test_content_ideas_read_model_summarizes_professional_decision_fields(
    monkeypatch,
) -> None:
    module = _read_model_module()
    monkeypatch.setattr(module, "generate_content_idea_bank", _idea_bank)

    payload = module.get_content_ideas_read_model().to_dict()
    idea = payload["recent_ideas"][0]

    assert idea["title"] == "Show ACE as a read-only window into ARI"
    assert idea["hook"] == "This is what an AI interface looks like without becoming the brain."
    assert idea["platform_fit"] == ("LinkedIn", "TikTok/Reel")
    assert idea["proof_point_count"] == 2
    assert idea["risk_level"] == "low"
    assert idea["recording_difficulty"] == "low"
    assert idea["edit_complexity"] == "low"
    assert idea["recommended_priority"] == 84
    assert idea["visual_plan"] == "Show ACE displaying ARI-owned read models."
    assert idea["script_angle"] == "Show the dashboard reading ARI state without controls."
    assert idea["redaction_note_count"] == 1
    assert idea["claims_to_avoid_count"] == 2
    assert idea["readiness_status"] == "ready_for_review"
    assert "api self-doc ideas list" in idea["inspection_hint"]


def test_content_ideas_read_model_marks_redaction_risk_conservatively(
    monkeypatch,
) -> None:
    module = _read_model_module()
    risky_idea = _idea(
        idea_id="content-idea-risky",
        risk_level="high",
        redaction_notes=("Review and redact possible token before recording.",),
    )
    monkeypatch.setattr(
        module,
        "generate_content_idea_bank",
        lambda *, db_path, limit: _idea_bank(ideas=(risky_idea,)),
    )

    payload = module.get_content_ideas_read_model().to_dict()

    assert payload["recent_ideas"][0]["readiness_status"] == "needs_redaction_review"


def test_content_ideas_read_model_represents_unavailable_storage(monkeypatch) -> None:
    module = _read_model_module()
    monkeypatch.setattr(
        module,
        "generate_content_idea_bank",
        lambda *, db_path, limit: ContentIdeaBank(
            generated_at="2026-05-06T00:00:00Z",
            total_idea_count=0,
            ideas=(),
            source_of_truth="persisted self-documentation artifacts",
            unavailable_reason=(
                "Content ideas are unavailable: RuntimeError: content artifact store offline"
            ),
            authority_warning="read-only",
        ),
    )

    payload = module.get_content_ideas_read_model().to_dict()

    assert payload["total_idea_count"] == 0
    assert payload["recent_ideas"] == ()
    assert "RuntimeError: content artifact store offline" in payload["unavailable_reason"]
    assert "ContentIdeaBank" in payload["source_of_truth"]


def test_content_ideas_read_model_is_read_only(monkeypatch) -> None:
    module = _read_model_module()
    calls: list[str] = []
    idea = _idea()
    before = idea.to_dict()

    def generate_only(*, db_path, limit):
        calls.append("generate-content-idea-bank")
        return _idea_bank(ideas=(idea,))

    monkeypatch.setattr(module, "generate_content_idea_bank", generate_only)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(f"unexpected external call: {args} {kwargs}")
        ),
    )

    payload = module.get_content_ideas_read_model().to_dict()

    assert calls == ["generate-content-idea-bank"]
    assert idea.to_dict() == before
    assert "must not generate ideas independently" in payload["authority_warning"]
    assert "must not generate ideas independently" in payload["authority_warning"]
    assert "must not" in payload["authority_warning"]


def _read_model_module():
    return importlib.import_module("ari_core.modules.overview.content_ideas")


def _idea_bank(
    *,
    db_path=None,
    limit=20,
    ideas: tuple[ContentIdea, ...] | None = None,
) -> ContentIdeaBank:
    del db_path, limit
    bank_ideas = ideas if ideas is not None else (_idea(),)
    return ContentIdeaBank(
        generated_at="2026-05-06T00:00:00Z",
        total_idea_count=len(bank_ideas),
        ideas=bank_ideas,
        source_of_truth="persisted self-documentation artifacts",
        unavailable_reason=None,
        authority_warning="read-only",
    )


def _idea(
    *,
    idea_id: str = "content-idea-read-model",
    risk_level: str = "low",
    redaction_notes: tuple[str, ...] = ("No sensitive-looking input was detected.",),
) -> ContentIdea:
    return ContentIdea(
        idea_id=idea_id,
        title="Show ACE as a read-only window into ARI",
        hook="This is what an AI interface looks like without becoming the brain.",
        platform_fit=("LinkedIn", "TikTok/Reel"),
        audience="product-minded AI builders and operators",
        source_artifact_ids=("content-package-read-model", "content-seed-read-model"),
        source_artifact_types=("content_package", "content_seed"),
        proof_points=(
            "Commit 7582c71: Show self-documentation artifacts in ACE",
            "ACE displays ARI-owned read models without controls.",
        ),
        visual_plan="Show ACE displaying ARI-owned read models.",
        suggested_shot_list=("Open ACE dashboard.", "Show disabled controls."),
        script_angle="Show the dashboard reading ARI state without controls.",
        recording_difficulty="low",
        edit_complexity="low",
        risk_level=risk_level,
        redaction_notes=redaction_notes,
        claims_to_avoid=(
            "Do not claim ACE owns decisions.",
            "Do not claim ARI records, edits, uploads, publishes, or posts content.",
        ),
        recommended_priority=84,
        reason_for_priority="Strong proof, low risk, and easy recording.",
        created_at="2026-05-06T00:00:00Z",
    )
