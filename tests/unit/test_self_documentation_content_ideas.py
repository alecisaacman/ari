from __future__ import annotations

import importlib
import json

from ari_core.modules.self_documentation import (
    ContentSeed,
    SourceCommit,
    generate_content_package_from_seed,
)


def test_content_idea_bank_is_json_serializable(monkeypatch) -> None:
    module = _ideas_module()
    monkeypatch.setattr(module, "list_content_seeds", _list_seeds)
    monkeypatch.setattr(module, "list_content_packages", _list_packages)

    payload = module.generate_content_idea_bank().to_dict()

    decoded = json.loads(json.dumps(payload))
    assert decoded["total_idea_count"] == 2
    assert decoded["ideas"][0]["idea_id"].startswith("content-idea-")


def test_content_ideas_are_produced_from_seeds_and_packages(monkeypatch) -> None:
    module = _ideas_module()
    monkeypatch.setattr(module, "list_content_seeds", _list_seeds)
    monkeypatch.setattr(module, "list_content_packages", _list_packages)

    payload = module.generate_content_idea_bank().to_dict()

    source_types = {
        tuple(idea["source_artifact_types"])
        for idea in payload["ideas"]
    }
    assert ("content_seed",) in source_types
    assert ("content_package", "content_seed") in source_types
    for idea in payload["ideas"]:
        assert idea["title"]
        assert idea["hook"]
        assert idea["visual_plan"]
        assert idea["platform_fit"]
        assert idea["proof_points"]


def test_content_ideas_preserve_claims_and_redaction_notes(monkeypatch) -> None:
    module = _ideas_module()
    monkeypatch.setattr(module, "list_content_seeds", _list_seeds)
    monkeypatch.setattr(module, "list_content_packages", lambda *, limit, db_path: ())

    idea = module.generate_content_idea_bank().to_dict()["ideas"][0]

    assert "No sensitive-looking input was detected." in idea["redaction_notes"]
    assert "Do not claim ARI posts content publicly." in idea["claims_to_avoid"]
    assert any("records, edits, uploads" in claim for claim in idea["claims_to_avoid"])


def test_content_idea_priority_is_deterministic(monkeypatch) -> None:
    module = _ideas_module()
    seed = _seed()
    monkeypatch.setattr(module, "list_content_seeds", lambda *, limit, db_path: (seed,))
    monkeypatch.setattr(module, "list_content_packages", lambda *, limit, db_path: ())

    first = module.generate_content_idea_bank().to_dict()["ideas"][0]
    second = module.generate_content_idea_bank().to_dict()["ideas"][0]

    assert first["idea_id"] == second["idea_id"]
    assert first["recommended_priority"] == second["recommended_priority"]
    assert first["risk_level"] == "low"


def test_content_ideas_compute_risk_without_exaggerated_claims(monkeypatch) -> None:
    module = _ideas_module()
    risky_seed = _seed(
        risk_notes=("Possible API key-like string detected.",),
        redaction_notes=("Review and redact secret-like content before public use.",),
    )
    monkeypatch.setattr(module, "list_content_seeds", lambda *, limit, db_path: (risky_seed,))
    monkeypatch.setattr(module, "list_content_packages", lambda *, limit, db_path: ())

    idea = module.generate_content_idea_bank().to_dict()["ideas"][0]

    assert idea["risk_level"] == "high"
    assert idea["recording_difficulty"] in {"low", "medium"}
    text = json.dumps(idea).lower()
    assert "records, edits, exports, uploads, or publishes media" in text
    assert "unattended autonomy" in text


def test_content_idea_bank_represents_unavailable_storage(monkeypatch) -> None:
    module = _ideas_module()

    def raise_unavailable(*, limit, db_path):
        raise RuntimeError("content artifact store offline")

    monkeypatch.setattr(module, "list_content_seeds", raise_unavailable)

    payload = module.generate_content_idea_bank().to_dict()

    assert payload["total_idea_count"] == 0
    assert payload["ideas"] == ()
    assert "RuntimeError: content artifact store offline" in payload["unavailable_reason"]
    assert "persisted self-documentation" in payload["source_of_truth"]


def test_content_idea_bank_does_not_call_external_services(monkeypatch) -> None:
    module = _ideas_module()
    calls: list[str] = []

    def list_seeds_only(*, limit, db_path):
        calls.append("list-seeds")
        return _list_seeds(limit=limit, db_path=db_path)

    def list_packages_only(*, limit, db_path):
        calls.append("list-packages")
        return _list_packages(limit=limit, db_path=db_path)

    monkeypatch.setattr(module, "list_content_seeds", list_seeds_only)
    monkeypatch.setattr(module, "list_content_packages", list_packages_only)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(f"unexpected external call: {args} {kwargs}")
        ),
    )

    bank = module.generate_content_idea_bank()

    assert bank.total_idea_count == 2
    assert calls == ["list-seeds", "list-packages"]


def test_content_idea_bank_does_not_mutate_artifacts(monkeypatch) -> None:
    module = _ideas_module()
    seed = _seed()
    package = generate_content_package_from_seed(seed)
    before_seed = seed.to_dict()
    before_package = package.to_dict()
    monkeypatch.setattr(module, "list_content_seeds", lambda *, limit, db_path: (seed,))
    monkeypatch.setattr(module, "list_content_packages", lambda *, limit, db_path: (package,))

    module.generate_content_idea_bank()

    assert seed.to_dict() == before_seed
    assert package.to_dict() == before_package


def _ideas_module():
    return importlib.import_module("ari_core.modules.self_documentation.content_ideas")


def _list_seeds(*, limit, db_path):
    del limit, db_path
    return (_seed(),)


def _list_packages(*, limit, db_path):
    del limit, db_path
    return (generate_content_package_from_seed(_seed()),)


def _seed(
    *,
    risk_notes: tuple[str, ...] = (),
    redaction_notes: tuple[str, ...] = ("No sensitive-looking input was detected.",),
) -> ContentSeed:
    return ContentSeed(
        seed_id="content-seed-ideas-test",
        source_commit_range="abc123..def456",
        source_commits=(
            SourceCommit(
                hash="def456789abc",
                subject="Show ACE read-only dashboard and self-documentation artifacts",
            ),
        ),
        source_files=(
            "services/ari-hub/app/page.tsx",
            "services/ari-core/src/ari_core/modules/overview/self_documentation.py",
        ),
        title="ACE displays ARI-owned self-documentation artifacts",
        one_sentence_summary="ACE now shows persisted content artifacts without owning truth.",
        why_it_matters="It keeps creator workflow planning grounded in ARI state.",
        proof_points=(
            "Commit def456789abc: Show self-documentation artifacts in ACE",
            "Read-only dashboard panel displays persisted artifact summaries.",
        ),
        demo_idea="Show the ACE dashboard reading ARI-owned self-documentation artifacts.",
        hook_options=("This is a dashboard that displays AI state without becoming the brain.",),
        visual_moments=(
            "Show the ACE dashboard self-documentation panel.",
            "Show CLI output for api overview self-documentation --json.",
        ),
        suggested_voiceover="ARI owns the content truth; ACE only displays it.",
        suggested_linkedin_post="Read-only ACE now displays ARI-owned content artifacts.",
        suggested_short_caption="ARI-owned content artifacts, ACE read-only.",
        risk_notes=risk_notes,
        redaction_notes=redaction_notes,
        claims_to_avoid=(
            "Do not claim ARI records, edits, exports, uploads, or publishes media.",
            "Do not claim ARI posts content publicly.",
        ),
        next_content_angle="Show content idea selection from persisted artifacts.",
        created_at="2026-05-06T00:00:00Z",
    )
