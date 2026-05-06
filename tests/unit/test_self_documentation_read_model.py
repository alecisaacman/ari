from __future__ import annotations

import importlib
import json

from ari_core.modules.self_documentation import (
    ContentSeed,
    SourceCommit,
    generate_content_package_from_seed,
)


def test_self_documentation_read_model_is_json_serializable(monkeypatch) -> None:
    module = _read_model_module()
    monkeypatch.setattr(module, "list_content_seeds", _list_seeds)
    monkeypatch.setattr(module, "list_content_packages", _list_packages)

    payload = module.get_self_documentation_read_model().to_dict()

    decoded = json.loads(json.dumps(payload))
    assert decoded["total_seed_count"] == 1
    assert decoded["total_package_count"] == 1
    assert decoded["recent_artifacts"][0]["artifact_id"]


def test_self_documentation_read_model_includes_seed_and_package_summaries(
    monkeypatch,
) -> None:
    module = _read_model_module()
    monkeypatch.setattr(module, "list_content_seeds", _list_seeds)
    monkeypatch.setattr(module, "list_content_packages", _list_packages)

    payload = module.get_self_documentation_read_model().to_dict()

    artifacts = {artifact["artifact_type"]: artifact for artifact in payload["recent_artifacts"]}
    seed = artifacts["content_seed"]
    assert seed["artifact_id"] == "content-seed-read-model"
    assert seed["title"] == "ARI preserves self-documentation artifacts"
    assert seed["summary"] == "ARI can inspect durable self-documentation artifacts."
    assert seed["source_commit_range"] == "abc123..def456"
    assert seed["proof_point_count"] == 2
    assert seed["visual_moment_count"] == 2
    assert seed["redaction_note_count"] == 1
    assert seed["claims_to_avoid_count"] == 1
    assert seed["has_voiceover_draft"] is True
    assert seed["has_caption"] is True
    assert seed["inspection_hint"] == (
        "api self-doc seeds show --id content-seed-read-model"
    )

    package = artifacts["content_package"]
    assert package["source_seed_id"] == "content-seed-read-model"
    assert package["has_shot_list"] is True
    assert package["has_terminal_demo_plan"] is True
    assert package["has_caption"] is True
    assert package["visual_moment_count"] == 3
    assert package["inspection_hint"].startswith("api self-doc packages show --id ")


def test_self_documentation_read_model_computes_readiness_conservatively(
    monkeypatch,
) -> None:
    module = _read_model_module()
    safe_seed = _seed()
    risky_seed = _seed(
        seed_id="content-seed-risky",
        risk_notes=("Possible API key-like string detected.",),
        redaction_notes=("Review and redact secret-like content before public use.",),
    )
    partial_seed = _seed(seed_id="content-seed-partial", proof_points=())
    monkeypatch.setattr(
        module,
        "list_content_seeds",
        lambda *, limit, db_path: (safe_seed, risky_seed, partial_seed),
    )
    monkeypatch.setattr(module, "list_content_packages", lambda *, limit, db_path: ())

    payload = module.get_self_documentation_read_model().to_dict()

    statuses = {
        artifact["artifact_id"]: artifact["readiness_status"]
        for artifact in payload["recent_artifacts"]
    }
    assert statuses["content-seed-read-model"] == "ready_for_review"
    assert statuses["content-seed-risky"] == "needs_redaction_review"
    assert statuses["content-seed-partial"] == "partial"


def test_self_documentation_read_model_represents_unavailable_storage(
    monkeypatch,
) -> None:
    module = _read_model_module()

    def raise_unavailable(*, limit, db_path):
        raise RuntimeError("self-doc store offline")

    monkeypatch.setattr(module, "list_content_seeds", raise_unavailable)

    payload = module.get_self_documentation_read_model().to_dict()

    assert payload["total_seed_count"] == 0
    assert payload["total_package_count"] == 0
    assert payload["recent_artifacts"] == ()
    assert "RuntimeError: self-doc store offline" in payload["unavailable_reason"]
    assert "durable self-documentation" in payload["source_of_truth"]


def test_self_documentation_read_model_is_read_only(monkeypatch) -> None:
    module = _read_model_module()
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

    payload = module.get_self_documentation_read_model().to_dict()

    assert calls == ["list-seeds", "list-packages"]
    assert "inspection-only" in payload["authority_warning"]
    assert "must not generate content" in payload["authority_warning"]


def _read_model_module():
    return importlib.import_module("ari_core.modules.overview.self_documentation")


def _list_seeds(*, limit, db_path):
    del limit, db_path
    return (_seed(),)


def _list_packages(*, limit, db_path):
    del limit, db_path
    return (generate_content_package_from_seed(_seed()),)


def _seed(
    *,
    seed_id: str = "content-seed-read-model",
    proof_points: tuple[str, ...] = (
        "Commit def456789abc: Persist self-documentation artifacts",
        "Changed self-documentation storage and tests.",
    ),
    risk_notes: tuple[str, ...] = (),
    redaction_notes: tuple[str, ...] = (
        "No sensitive-looking input was detected by the first-pass scanner.",
    ),
) -> ContentSeed:
    return ContentSeed(
        seed_id=seed_id,
        source_commit_range="abc123..def456",
        source_commits=(
            SourceCommit(
                hash="def456789abc",
                subject="Persist self-documentation artifacts",
            ),
        ),
        source_files=(
            "services/ari-core/src/ari_core/modules/self_documentation/storage.py",
            "tests/unit/test_self_documentation_storage.py",
        ),
        title="ARI preserves self-documentation artifacts",
        one_sentence_summary="ARI can inspect durable self-documentation artifacts.",
        why_it_matters="It keeps creator workflow state grounded in ARI-owned storage.",
        proof_points=proof_points,
        demo_idea="Show persisted artifacts through read-only inspection.",
        hook_options=("ARI can keep its build story durable and reviewable.",),
        visual_moments=(
            "Show persisted ContentSeed fields.",
            "Show persisted ContentPackage fields.",
        ),
        suggested_voiceover="ARI stores content planning artifacts locally.",
        suggested_linkedin_post="ARI self-documentation now has durable artifacts.",
        suggested_short_caption="Durable ARI content artifacts.",
        risk_notes=risk_notes,
        redaction_notes=redaction_notes,
        claims_to_avoid=("Do not claim ARI records or publishes content.",),
        next_content_angle="Show read-only artifact inspection in ACE.",
        created_at="2026-05-06T00:00:00Z",
    )
