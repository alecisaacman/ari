from __future__ import annotations

import json
from pathlib import Path

from ari_core.modules.self_documentation import (
    ContentSeed,
    SourceCommit,
    generate_content_package_from_seed,
)


def _seed() -> ContentSeed:
    return ContentSeed(
        seed_id="content-seed-test",
        source_commit_range="abc123..def456",
        source_commits=(
            SourceCommit(
                hash="def456789abc",
                subject="Generate self-documentation content seeds",
            ),
        ),
        source_files=(
            "services/ari-core/src/ari_core/modules/self_documentation/content_seed.py",
            "tests/unit/test_self_documentation_content_seed.py",
        ),
        title="ARI starts turning its own build history into content seeds",
        one_sentence_summary=(
            "This seed summarizes 1 commit touching 2 files, with primary themes: "
            "self_documentation."
        ),
        why_it_matters=(
            "It gives ARI a factual path to explain and demonstrate its own build "
            "process without inventing progress."
        ),
        proof_points=(
            "Commit def456789abc: Generate self-documentation content seeds",
            (
                "Changed 2 file(s): "
                "services/ari-core/src/ari_core/modules/self_documentation/content_seed.py, "
                "tests/unit/test_self_documentation_content_seed.py."
            ),
            "Test output supplied: 183 passed",
        ),
        demo_idea=(
            "Show a commit range becoming a factual content seed with risks and "
            "claims-to-avoid."
        ),
        hook_options=(
            "What if your AI system could document its own build without making things up?",
            "ARI is learning how to turn real commits into factual demos.",
        ),
        visual_moments=(
            "Show the commit range and changed files used as evidence.",
            "Show the generated ContentSeed fields and claims_to_avoid.",
        ),
        suggested_voiceover=(
            "ARI starts turning its own build history into content seeds. Proof point: "
            "Commit def456789abc."
        ),
        suggested_linkedin_post=(
            "ARI starts turning its own build history into content seeds\n\nEvidence:\n"
            "- Commit def456789abc: Generate self-documentation content seeds"
        ),
        suggested_short_caption=(
            "ARI is turning real build evidence into factual content seeds."
        ),
        risk_notes=("No sensitive-looking input was detected by the first-pass scanner.",),
        redaction_notes=("No sensitive-looking input was detected by the first-pass scanner.",),
        claims_to_avoid=(
            "Do not claim this feature records, edits, exports, or publishes media.",
            "Do not claim ARI has a runtime skill registry.",
        ),
        next_content_angle=(
            "Show the first implementation generating a seed from a commit range."
        ),
        created_at="2026-05-05T00:00:00Z",
    )


def test_content_package_generated_from_content_seed() -> None:
    seed = _seed()

    package = generate_content_package_from_seed(seed)

    assert package.package_id.startswith("content-package-")
    assert package.source_seed_id == seed.seed_id
    assert package.title == seed.title
    assert package.content_angle == seed.next_content_angle
    assert seed.one_sentence_summary in package.thirty_second_vertical_script
    assert "Commit def456789abc" in package.thirty_second_vertical_script
    assert "183 passed" in package.sixty_second_linkedin_script
    assert package.voiceover_draft == seed.suggested_voiceover
    assert package.linkedin_post == seed.suggested_linkedin_post
    assert package.short_caption == seed.suggested_short_caption


def test_content_package_has_shots_demo_plan_and_safety_boundaries() -> None:
    package = generate_content_package_from_seed(_seed())

    assert [shot.label for shot in package.shot_list] == [
        "Evidence",
        "Why It Matters",
        "Boundary",
    ]
    assert package.terminal_demo_plan
    assert package.terminal_demo_plan[0].command_or_action.startswith(
        "api self-doc seed from-commits"
    )
    assert "Read-only local git inspection" in package.terminal_demo_plan[0].safety_note
    assert package.claims_to_avoid == _seed().claims_to_avoid
    assert package.redaction_checklist
    assert any("API keys" in item for item in package.redaction_checklist)
    assert package.approval_required_before_recording is True
    assert package.approval_required_before_posting is True


def test_content_package_is_json_serializable_and_non_persistent(tmp_path: Path) -> None:
    before_paths = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    package = generate_content_package_from_seed(_seed())
    payload = package.to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    after_paths = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    assert decoded["source_seed_id"] == "content-seed-test"
    assert decoded["shot_list"][0]["label"] == "Evidence"
    assert decoded["terminal_demo_plan"][0]["expected_result"]
    assert decoded["approval_required_before_recording"] is True
    assert after_paths == before_paths


def test_content_package_does_not_call_external_services(monkeypatch) -> None:
    def fail_external(*args, **kwargs):
        raise AssertionError(f"unexpected external call: {args} {kwargs}")

    monkeypatch.setattr("subprocess.run", fail_external)

    package = generate_content_package_from_seed(_seed())

    assert package.source_seed_id == "content-seed-test"
    assert package.approval_required_before_recording is True
    assert package.approval_required_before_posting is True
