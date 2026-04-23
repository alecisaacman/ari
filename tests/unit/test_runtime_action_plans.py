from __future__ import annotations

from pathlib import Path

from ari_core.runtime.action_plans import build_action_plan
from ari_core.runtime.self_improvement_runner import ImprovementSlice, SliceSelection
from ari_core.runtime.verification_profiles import verification_profile_for_slice


def test_build_action_plan_creates_bounded_prompt_and_expectations(tmp_path: Path) -> None:
    slice_spec = ImprovementSlice(
        key="governed-coding-loop-quality",
        title="Strengthen governed coding loop quality",
        prompt_hint="Improve controller-quality slice selection and verification.",
        milestone="governed coding loop",
        priority=100,
        expected_paths=(
            "services/ari-core/src/ari_core/runtime/self_improvement_runner.py",
        ),
        expected_symbols={
            "services/ari-core/src/ari_core/runtime/self_improvement_runner.py": ("ControllerDecisionRecord",),
        },
    )
    selection = SliceSelection(
        slice_spec=slice_spec,
        reason="Chosen because the milestone and missing symbols align with the goal.",
        score=150,
        evidence={"missingPaths": [], "missingSymbols": {"services/ari-core/src/ari_core/runtime/self_improvement_runner.py": ["ControllerDecisionRecord"]}},
    )
    profile = verification_profile_for_slice(slice_spec)

    plan = build_action_plan(
        goal="Strengthen ARI's governed coding loop safely",
        selection=selection,
        verification_profile=profile,
    )

    assert plan.slice_key == "governed-coding-loop-quality"
    assert plan.attempt_kind == "initial"
    assert "services/ari-core/src/ari_core/runtime/self_improvement_runner.py" in plan.likely_files
    assert any("ControllerDecisionRecord" in expectation for expectation in plan.verification_expectations)
    assert "Codex, acting as a bounded coding worker under ARI's control." in plan.prompt_text
    assert "Constraints:" in plan.prompt_text
