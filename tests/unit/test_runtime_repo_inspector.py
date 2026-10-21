from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from ari_core.modules.execution import RuntimeExecutionAdapter
from ari_core.runtime.repo_inspector import RepoInspectionResult, inspect_repo_state
from ari_core.runtime.verification_profiles import canonical_command_runner


def test_repo_inspector_reports_git_file_and_symbol_state(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    target = tmp_path / "target.py"
    target.write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    (tmp_path / "test_target.py").write_text(
        "from target import hello\n\n\ndef test_hello():\n    assert hello() == 'world'\n",
        encoding="utf-8",
    )
    # Verification commands run as canonical ARI steps, recorded in a ledger kept
    # outside the inspected repository.
    ledger_path = tmp_path_factory.mktemp("ledger") / "ari.db"
    runner = canonical_command_runner(RuntimeExecutionAdapter(ledger_path, execution_root=tmp_path))

    result = inspect_repo_state(
        tmp_path,
        expected_paths=["target.py"],
        expected_symbols={"target.py": ["hello"]},
        verification_commands=[(sys.executable, "-m", "pytest", "test_target.py", "-q")],
        command_runner=runner,
    )

    assert isinstance(result, RepoInspectionResult)
    assert result.git_available is True
    assert result.git_dirty is True
    assert "target.py" in result.changed_paths
    assert isinstance(result.diff_summary, str)
    assert result.expected_paths_present["target.py"] is True
    assert result.expected_paths_changed["target.py"] is True
    assert result.expected_paths_touched["target.py"] is True
    assert result.symbol_matches["target.py"]["hello"] is True
    assert result.verification_passed is True
    assert len(result.verification_runs) == 1
    assert result.tests_passed is True
