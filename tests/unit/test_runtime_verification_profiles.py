from __future__ import annotations

from pathlib import Path

from ari_core.runtime.repo_inspector import RepoInspectionResult
from ari_core.runtime.verification_profiles import (
    FileChanged,
    OutputMatches,
    SymbolExists,
    VerificationContext,
    VerificationProfile,
    evaluate_profile,
)


def _inspection(
    *,
    repo_root: Path,
    changed_paths: list[str],
    expected_paths_present: dict[str, bool],
    expected_paths_touched: dict[str, bool],
    symbol_matches: dict[str, dict[str, bool]],
) -> RepoInspectionResult:
    return RepoInspectionResult(
        repo_root=str(repo_root),
        git_available=True,
        git_dirty=bool(changed_paths),
        changed_paths=changed_paths,
        diff_summary="1 file changed",
        newly_changed_paths=changed_paths,
        expected_paths_present=expected_paths_present,
        expected_paths_changed={path: True for path in changed_paths},
        expected_paths_touched=expected_paths_touched,
        symbol_matches=symbol_matches,
        verification_runs=[],
        verification_passed=False,
        tests_passed=False,
    )


def test_verification_profile_classifies_success_when_all_required_checks_pass(tmp_path: Path) -> None:
    context = VerificationContext(
        repo_root=tmp_path,
        pre_inspection=_inspection(
            repo_root=tmp_path,
            changed_paths=[],
            expected_paths_present={"target.py": False},
            expected_paths_touched={"target.py": False},
            symbol_matches={"target.py": {"READY": False}},
        ),
        post_inspection=_inspection(
            repo_root=tmp_path,
            changed_paths=["target.py"],
            expected_paths_present={"target.py": True},
            expected_paths_touched={"target.py": True},
            symbol_matches={"target.py": {"READY": True}},
        ),
        worker_stdout="READY implemented",
        worker_stderr="",
        worker_exit_code=0,
    )
    profile = VerificationProfile(
        slice_key="test-slice",
        checks=[
            FileChanged("target.py"),
            SymbolExists("target.py", "READY"),
            OutputMatches("READY", required=False),
        ],
    )

    result = evaluate_profile(profile, context)

    assert result.classification == "success"
    assert result.confidence_score >= 0.8
    assert not result.failed_checks


def test_verification_profile_classifies_partial_success_when_only_optional_check_fails(tmp_path: Path) -> None:
    context = VerificationContext(
        repo_root=tmp_path,
        pre_inspection=_inspection(
            repo_root=tmp_path,
            changed_paths=[],
            expected_paths_present={"target.py": False},
            expected_paths_touched={"target.py": False},
            symbol_matches={"target.py": {"READY": False}},
        ),
        post_inspection=_inspection(
            repo_root=tmp_path,
            changed_paths=["target.py"],
            expected_paths_present={"target.py": True},
            expected_paths_touched={"target.py": True},
            symbol_matches={"target.py": {"READY": True}},
        ),
        worker_stdout="implemented change",
        worker_stderr="",
        worker_exit_code=0,
    )
    profile = VerificationProfile(
        slice_key="test-slice",
        checks=[
            FileChanged("target.py"),
            SymbolExists("target.py", "READY"),
            OutputMatches("READY", required=False),
        ],
    )

    result = evaluate_profile(profile, context)

    assert result.classification == "partial_success"
    assert any(check.description.startswith("OutputMatches") for check in result.failed_checks)


def test_verification_profile_classifies_failure_when_required_check_fails(tmp_path: Path) -> None:
    context = VerificationContext(
        repo_root=tmp_path,
        pre_inspection=_inspection(
            repo_root=tmp_path,
            changed_paths=[],
            expected_paths_present={"target.py": False},
            expected_paths_touched={"target.py": False},
            symbol_matches={"target.py": {"READY": False}},
        ),
        post_inspection=_inspection(
            repo_root=tmp_path,
            changed_paths=[],
            expected_paths_present={"target.py": False},
            expected_paths_touched={"target.py": False},
            symbol_matches={"target.py": {"READY": False}},
        ),
        worker_stdout="implemented change",
        worker_stderr="",
        worker_exit_code=0,
    )
    profile = VerificationProfile(
        slice_key="test-slice",
        checks=[
            FileChanged("target.py"),
            SymbolExists("target.py", "READY"),
        ],
    )

    result = evaluate_profile(profile, context)

    assert result.classification == "failure"
    assert len(result.failed_checks) == 2
