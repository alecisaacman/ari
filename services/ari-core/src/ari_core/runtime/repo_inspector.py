from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from ari_core.core.git_inspection import run_git_inspection


@dataclass(frozen=True, slots=True)
class VerificationCommandResult:
    command: list[str]
    success: bool
    exit_code: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RepoInspectionResult:
    repo_root: str
    git_available: bool
    git_dirty: bool
    changed_paths: list[str]
    diff_summary: str
    newly_changed_paths: list[str]
    expected_paths_present: dict[str, bool]
    expected_paths_changed: dict[str, bool]
    expected_paths_touched: dict[str, bool]
    symbol_matches: dict[str, dict[str, bool]]
    verification_runs: list[VerificationCommandResult]
    verification_passed: bool
    tests_passed: bool

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["verificationRuns"] = [run.to_dict() for run in self.verification_runs]
        return payload


def inspect_repo_state(
    repo_root: Path | str,
    *,
    expected_paths: Sequence[str] = (),
    expected_symbols: Mapping[str, Sequence[str]] | None = None,
    changed_paths_baseline: Sequence[str] = (),
    verification_commands: Sequence[Sequence[str]] = (),
    worker_stdout: str = "",
    worker_stderr: str = "",
    worker_exit_code: int | None = None,
    command_runner: Callable[[Sequence[str]], object] | None = None,
) -> RepoInspectionResult:
    root = Path(repo_root).expanduser().resolve()
    changed_paths, diff_summary, git_available = _git_changed_paths(root)
    expected_path_presence = {
        path: (root / path).exists()
        for path in expected_paths
    }
    changed_path_set = set(changed_paths)
    baseline_set = set(changed_paths_baseline)
    newly_changed_paths = [path for path in changed_paths if path not in baseline_set]
    newly_changed_set = set(newly_changed_paths)
    expected_path_changes = {
        path: path in changed_path_set
        for path in expected_paths
    }
    expected_path_touches = {
        path: path in newly_changed_set
        for path in expected_paths
    }
    symbol_results = _symbol_matches(root, expected_symbols or {})
    verification_runs = _run_verification_commands(root, verification_commands, command_runner)
    verification_passed = all(run.success for run in verification_runs) if verification_runs else False
    tests_passed = verification_passed and any(_looks_like_test_command(run.command) for run in verification_runs)
    if not verification_runs:
        tests_passed = _tests_passed(worker_stdout, worker_stderr, worker_exit_code)
    return RepoInspectionResult(
        repo_root=str(root),
        git_available=git_available,
        git_dirty=bool(changed_paths),
        changed_paths=changed_paths,
        diff_summary=diff_summary,
        newly_changed_paths=newly_changed_paths,
        expected_paths_present=expected_path_presence,
        expected_paths_changed=expected_path_changes,
        expected_paths_touched=expected_path_touches,
        symbol_matches=symbol_results,
        verification_runs=verification_runs,
        verification_passed=verification_passed,
        tests_passed=tests_passed,
    )


def _git_changed_paths(repo_root: Path) -> tuple[list[str], str, bool]:
    try:
        completed = run_git_inspection(["status", "--short"], repo_root, timeout=15)
        diff_completed = run_git_inspection(["diff", "--shortstat"], repo_root, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return [], "", False

    if completed.returncode != 0:
        return [], "", False

    changed_paths: list[str] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        payload = line[3:].strip() if len(line) >= 3 else line.strip()
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1].strip()
        changed_paths.append(payload)
    diff_summary = diff_completed.stdout.strip() if diff_completed.returncode == 0 else ""
    return changed_paths, diff_summary, True


def _symbol_matches(repo_root: Path, expected_symbols: Mapping[str, Sequence[str]]) -> dict[str, dict[str, bool]]:
    results: dict[str, dict[str, bool]] = {}
    for relative_path, symbols in expected_symbols.items():
        file_path = repo_root / relative_path
        if not file_path.exists():
            results[relative_path] = {symbol: False for symbol in symbols}
            continue
        content = file_path.read_text(encoding="utf-8")
        results[relative_path] = {
            symbol: symbol in content
            for symbol in symbols
        }
    return results


def _run_verification_commands(
    repo_root: Path,
    commands: Sequence[Sequence[str]],
    command_runner: Callable[[Sequence[str]], object] | None,
) -> list[VerificationCommandResult]:
    if not commands:
        return []
    if command_runner is None:
        # Imported here: verification_profiles depends on this module.
        from .verification_profiles import default_command_runner

        command_runner = default_command_runner(repo_root)
    results: list[VerificationCommandResult] = []
    for command in commands:
        completed = command_runner(command)
        results.append(
            VerificationCommandResult(
                command=list(command),
                success=bool(getattr(completed, "success", False)),
                exit_code=int(getattr(completed, "exit_code", -1)),
                stdout=str(getattr(completed, "stdout", "")),
                stderr=str(getattr(completed, "stderr", "")),
            )
        )
    return results


def _looks_like_test_command(command: Sequence[str]) -> bool:
    joined = " ".join(command).lower()
    return "pytest" in joined or "--test" in joined


def _tests_passed(stdout: str, stderr: str, exit_code: int | None) -> bool:
    if exit_code is None or exit_code != 0:
        return False
    combined = f"{stdout}\n{stderr}".lower()
    positive_patterns = (" passed", "0 failed", "build succeeded", "build successful")
    negative_patterns = (" failed", "error:", "traceback", "exception")
    return any(pattern in combined for pattern in positive_patterns) and not any(
        pattern in combined for pattern in negative_patterns
    )
