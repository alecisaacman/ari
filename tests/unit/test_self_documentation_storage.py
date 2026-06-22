from __future__ import annotations

import json
from pathlib import Path

from ari_core.modules.self_documentation import (
    ContentSeed,
    SourceCommit,
    generate_content_package_from_seed,
    get_content_package,
    get_content_seed,
    list_content_packages,
    list_content_seeds,
    store_content_package,
    store_content_seed,
)


def test_content_seed_can_be_persisted_and_retrieved(tmp_path: Path) -> None:
    db_path = tmp_path / "ari.db"
    seed = _seed()

    stored = store_content_seed(seed, db_path=db_path)
    retrieved = get_content_seed(seed.seed_id, db_path=db_path)

    assert stored == seed
    assert retrieved == seed
    assert retrieved is not None
    payload = retrieved.to_dict()
    assert json.loads(json.dumps(payload))["seed_id"] == "content-seed-storage-test"
    assert payload["redaction_notes"] == (
        "No sensitive-looking input was detected by the first-pass scanner.",
    )
    assert payload["claims_to_avoid"] == (
        "Do not claim this feature records, edits, exports, or publishes media.",
        "Do not claim ARI posts content publicly.",
    )
    assert "Commit def456789abc" in " ".join(payload["proof_points"])
    assert payload["visual_moments"] == (
        "Show the commit range and changed files used as evidence.",
        "Show the generated ContentSeed fields and claims_to_avoid.",
    )


def test_content_package_can_be_persisted_and_retrieved(tmp_path: Path) -> None:
    db_path = tmp_path / "ari.db"
    seed = _seed()
    package = generate_content_package_from_seed(seed)

    stored = store_content_package(package, db_path=db_path)
    retrieved = get_content_package(package.package_id, db_path=db_path)

    assert stored == package
    assert retrieved == package
    assert retrieved is not None
    payload = retrieved.to_dict()
    decoded = json.loads(json.dumps(payload))
    assert decoded["package_id"] == package.package_id
    assert decoded["source_seed_id"] == seed.seed_id
    assert decoded["voiceover_draft"] == seed.suggested_voiceover
    assert decoded["short_caption"] == seed.suggested_short_caption
    assert decoded["shot_list"][0]["label"] == "Evidence"
    assert decoded["terminal_demo_plan"][0]["command_or_action"].startswith(
        "api self-doc seed from-commits"
    )
    assert decoded["claims_to_avoid"] == [
        "Do not claim this feature records, edits, exports, or publishes media.",
        "Do not claim ARI posts content publicly.",
    ]


def test_content_artifact_lists_return_recent_items(tmp_path: Path) -> None:
    db_path = tmp_path / "ari.db"
    first_seed = _seed(seed_id="content-seed-first", created_at="2026-05-05T00:00:00Z")
    second_seed = _seed(
        seed_id="content-seed-second",
        created_at="2026-05-05T00:01:00Z",
    )
    first_package = generate_content_package_from_seed(first_seed)
    second_package = generate_content_package_from_seed(second_seed)

    store_content_seed(first_seed, db_path=db_path)
    store_content_seed(second_seed, db_path=db_path)
    store_content_package(first_package, db_path=db_path)
    store_content_package(second_package, db_path=db_path)

    seeds = list_content_seeds(limit=10, db_path=db_path)
    packages = list_content_packages(limit=10, db_path=db_path)

    assert {seed.seed_id for seed in seeds} == {"content-seed-first", "content-seed-second"}
    assert {package.package_id for package in packages} == {
        first_package.package_id,
        second_package.package_id,
    }


def test_unknown_content_artifact_ids_fail_safely(tmp_path: Path) -> None:
    db_path = tmp_path / "ari.db"

    assert get_content_seed("missing-seed", db_path=db_path) is None
    assert get_content_package("missing-package", db_path=db_path) is None


def test_content_artifact_storage_does_not_call_external_services(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_external(*args, **kwargs):
        raise AssertionError(f"unexpected external call: {args} {kwargs}")

    monkeypatch.setattr("subprocess.run", fail_external)
    db_path = tmp_path / "ari.db"
    seed = _seed()
    package = generate_content_package_from_seed(seed)

    store_content_seed(seed, db_path=db_path)
    store_content_package(package, db_path=db_path)

    assert get_content_seed(seed.seed_id, db_path=db_path) == seed
    assert get_content_package(package.package_id, db_path=db_path) == package


def _seed(
    *,
    seed_id: str = "content-seed-storage-test",
    created_at: str = "2026-05-05T00:00:00Z",
) -> ContentSeed:
    return ContentSeed(
        seed_id=seed_id,
        source_commit_range="abc123..def456",
        source_commits=(
            SourceCommit(
                hash="def456789abc",
                subject="Persist self-documentation content artifacts",
            ),
        ),
        source_files=(
            "services/ari-core/src/ari_core/modules/self_documentation/storage.py",
            "tests/unit/test_self_documentation_storage.py",
        ),
        title="ARI preserves self-documentation artifacts for review",
        one_sentence_summary=(
            "ARI can persist content seeds and packages as durable local artifacts."
        ),
        why_it_matters=(
            "It gives the creator workflow a factual source of truth before recording "
            "or publishing exists."
        ),
        proof_points=(
            "Commit def456789abc: Persist self-documentation content artifacts",
            "Changed storage and tests for durable local inspection.",
        ),
        demo_idea="Show persisted seeds and packages through read-only CLI inspection.",
        hook_options=("ARI is making its build story durable before making it flashy.",),
        visual_moments=(
            "Show the commit range and changed files used as evidence.",
            "Show the generated ContentSeed fields and claims_to_avoid.",
        ),
        suggested_voiceover=(
            "ARI is preserving factual self-documentation artifacts as local state."
        ),
        suggested_linkedin_post=(
            "ARI is turning build evidence into durable creator workflow artifacts."
        ),
        suggested_short_caption="Durable content artifacts, grounded in ARI build evidence.",
        risk_notes=("No sensitive-looking input was detected by the first-pass scanner.",),
        redaction_notes=("No sensitive-looking input was detected by the first-pass scanner.",),
        claims_to_avoid=(
            "Do not claim this feature records, edits, exports, or publishes media.",
            "Do not claim ARI posts content publicly.",
        ),
        next_content_angle="Show package generation from persisted seed evidence.",
        created_at=created_at,
    )
