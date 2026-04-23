from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Literal, Sequence

from .repo_inspector import RepoInspectionResult, VerificationCommandResult


CheckClassification = Literal["success", "partial_success", "failure"]


@dataclass(frozen=True, slots=True)
class VerificationCheckResult:
    check_type: str
    description: str
    passed: bool
    required: bool
    details: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VerificationResult:
    passed_checks: list[VerificationCheckResult]
    failed_checks: list[VerificationCheckResult]
    confidence_score: float
    classification: CheckClassification

    def to_dict(self) -> dict[str, object]:
        return {
            "passedChecks": [check.to_dict() for check in self.passed_checks],
            "failedChecks": [check.to_dict() for check in self.failed_checks],
            "confidenceScore": self.confidence_score,
            "classification": self.classification,
        }


@dataclass(frozen=True, slots=True)
class VerificationContext:
    repo_root: Path
    pre_inspection: RepoInspectionResult
    post_inspection: RepoInspectionResult
    worker_stdout: str
    worker_stderr: str
    worker_exit_code: int | None


class Check:
    required: bool

    def evaluate(self, context: VerificationContext) -> VerificationCheckResult:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class FileChanged(Check):
    path: str
    required: bool = True

    def evaluate(self, context: VerificationContext) -> VerificationCheckResult:
        touched = context.post_inspection.expected_paths_touched.get(self.path)
        present = context.post_inspection.expected_paths_present.get(self.path, (context.repo_root / self.path).exists())
        passed = bool(touched) if context.post_inspection.git_available else bool(present)
        details = "path changed in the current git diff" if passed and context.post_inspection.git_available else "path exists after the worker run" if passed else "path was not changed by the current cycle"
        return VerificationCheckResult(
            check_type="FileChanged",
            description=f"FileChanged({self.path})",
            passed=passed,
            required=self.required,
            details=details,
        )


@dataclass(frozen=True, slots=True)
class SymbolExists(Check):
    path: str
    name: str
    required: bool = True

    def evaluate(self, context: VerificationContext) -> VerificationCheckResult:
        path_matches = context.post_inspection.symbol_matches.get(self.path, {})
        passed = bool(path_matches.get(self.name, False))
        details = f"symbol '{self.name}' {'present' if passed else 'missing'} in {self.path}"
        return VerificationCheckResult(
            check_type="SymbolExists",
            description=f"SymbolExists({self.path}:{self.name})",
            passed=passed,
            required=self.required,
            details=details,
        )


@dataclass(frozen=True, slots=True)
class TestPasses(Check):
    path: str
    required: bool = True

    def evaluate(self, context: VerificationContext) -> VerificationCheckResult:
        command = [sys.executable, "-m", "pytest", self.path, "-q"]
        result = _run_command(command, context.repo_root)
        details = f"{self.path} {'passed' if result.success else 'failed'}"
        return VerificationCheckResult(
            check_type="TestPasses",
            description=f"TestPasses({self.path})",
            passed=result.success,
            required=self.required,
            details=details,
        )


@dataclass(frozen=True, slots=True)
class OutputMatches(Check):
    pattern: str
    source: Literal["stdout", "stderr", "combined"] = "stdout"
    required: bool = False

    def evaluate(self, context: VerificationContext) -> VerificationCheckResult:
        if self.source == "stdout":
            payload = context.worker_stdout
        elif self.source == "stderr":
            payload = context.worker_stderr
        else:
            payload = f"{context.worker_stdout}\n{context.worker_stderr}"
        passed = re.search(self.pattern, payload, flags=re.IGNORECASE) is not None
        details = f"pattern '{self.pattern}' {'matched' if passed else 'did not match'} {self.source}"
        return VerificationCheckResult(
            check_type="OutputMatches",
            description=f"OutputMatches({self.pattern})",
            passed=passed,
            required=self.required,
            details=details,
        )


@dataclass(frozen=True, slots=True)
class NoUnexpectedChanges(Check):
    allowed_paths: tuple[str, ...]
    required: bool = True

    def evaluate(self, context: VerificationContext) -> VerificationCheckResult:
        if not context.post_inspection.git_available:
            return VerificationCheckResult(
                check_type="NoUnexpectedChanges",
                description="NoUnexpectedChanges(git unavailable)",
                passed=True,
                required=self.required,
                details="git unavailable; unexpected-change check skipped",
            )

        allowed = set(self.allowed_paths)
        changed = set(context.post_inspection.changed_paths)
        unexpected = sorted(path for path in changed if path not in allowed)
        passed = not unexpected
        details = "no unexpected changed paths" if passed else f"unexpected changed paths: {', '.join(unexpected)}"
        return VerificationCheckResult(
            check_type="NoUnexpectedChanges",
            description="NoUnexpectedChanges",
            passed=passed,
            required=self.required,
            details=details,
        )


CustomCheckCallable = Callable[[VerificationContext, dict[str, object]], VerificationCheckResult]


@dataclass(frozen=True, slots=True)
class OptionalCustomCheck(Check):
    name: str
    config: dict[str, object] = field(default_factory=dict)
    required: bool = False

    def evaluate(self, context: VerificationContext) -> VerificationCheckResult:
        handler = CUSTOM_CHECKS.get(self.name)
        if handler is None:
            return VerificationCheckResult(
                check_type="OptionalCustomCheck",
                description=f"OptionalCustomCheck({self.name})",
                passed=False,
                required=self.required,
                details=f"custom check '{self.name}' is not registered",
            )
        return handler(context, self.config)


@dataclass(frozen=True, slots=True)
class VerificationProfile:
    slice_key: str
    checks: list[Check]

    def to_dict(self) -> dict[str, object]:
        return {
            "sliceKey": self.slice_key,
            "checks": [type(check).__name__ for check in self.checks],
        }


@dataclass(frozen=True, slots=True)
class CommandExecutionResult:
    command: list[str]
    success: bool
    exit_code: int
    stdout: str
    stderr: str


def evaluate_profile(profile: VerificationProfile, context: VerificationContext) -> VerificationResult:
    results = [check.evaluate(context) for check in profile.checks]
    passed_checks = [result for result in results if result.passed]
    failed_checks = [result for result in results if not result.passed]
    required_failures = [result for result in failed_checks if result.required]
    optional_failures = [result for result in failed_checks if not result.required]

    if required_failures:
        classification: CheckClassification = "failure"
    elif optional_failures:
        classification = "partial_success"
    else:
        classification = "success"

    confidence = round(len(passed_checks) / max(1, len(results)), 2)
    if classification == "failure":
        confidence = min(confidence, 0.49)
    elif classification == "partial_success":
        confidence = min(max(confidence, 0.5), 0.79)
    else:
        confidence = max(confidence, 0.8)

    return VerificationResult(
        passed_checks=passed_checks,
        failed_checks=failed_checks,
        confidence_score=confidence,
        classification=classification,
    )


def verification_profile_for_slice(slice_spec) -> VerificationProfile:
    registered = _registered_profiles().get(slice_spec.key)
    if registered is not None:
        return registered
    return _build_profile_from_slice(slice_spec)


def _registered_profiles() -> dict[str, VerificationProfile]:
    return {
        "governed-coding-loop-quality": VerificationProfile(
            slice_key="governed-coding-loop-quality",
            checks=[
                FileChanged("services/ari-core/src/ari_core/runtime/self_improvement_runner.py"),
                FileChanged("services/ari-core/src/ari_core/runtime/repo_inspector.py"),
                SymbolExists("services/ari-core/src/ari_core/runtime/self_improvement_runner.py", "ControllerDecisionRecord"),
                SymbolExists("services/ari-core/src/ari_core/runtime/repo_inspector.py", "verification_runs"),
                TestPasses("tests/unit/test_runtime_repo_inspector.py"),
                TestPasses("tests/unit/test_runtime_self_improvement_runner.py"),
                TestPasses("tests/unit/test_runtime_loop_runner.py"),
                NoUnexpectedChanges(
                    (
                        "services/ari-core/src/ari_core/runtime/self_improvement_runner.py",
                        "services/ari-core/src/ari_core/runtime/repo_inspector.py",
                        "services/ari-core/src/ari_core/modules/coordination/db.py",
                        "config/schema.sql",
                        "tests/unit/test_runtime_repo_inspector.py",
                        "tests/unit/test_runtime_self_improvement_runner.py",
                        "tests/unit/test_runtime_loop_runner.py",
                    )
                ),
            ],
        ),
        "governed-controller-trace": VerificationProfile(
            slice_key="governed-controller-trace",
            checks=[
                FileChanged("services/ari-core/src/ari_core/runtime/self_improvement_runner.py"),
                FileChanged("services/ari-core/src/ari_core/modules/coordination/db.py"),
                FileChanged("config/schema.sql"),
                SymbolExists("services/ari-core/src/ari_core/runtime/self_improvement_runner.py", "_persist_controller_decision"),
                SymbolExists("services/ari-core/src/ari_core/modules/coordination/db.py", "runtime_controller_decision"),
                SymbolExists("config/schema.sql", "ari_runtime_controller_decisions"),
                TestPasses("tests/unit/test_runtime_self_improvement_runner.py"),
                NoUnexpectedChanges(
                    (
                        "services/ari-core/src/ari_core/runtime/self_improvement_runner.py",
                        "services/ari-core/src/ari_core/modules/coordination/db.py",
                        "config/schema.sql",
                        "tests/unit/test_runtime_self_improvement_runner.py",
                    )
                ),
            ],
        ),
        "runtime-loop-hardening": VerificationProfile(
            slice_key="runtime-loop-hardening",
            checks=[
                FileChanged("services/ari-core/src/ari_core/runtime/loop_runner.py"),
                SymbolExists("services/ari-core/src/ari_core/runtime/loop_runner.py", "_evaluate_worker_result"),
                TestPasses("tests/unit/test_runtime_loop_runner.py"),
                NoUnexpectedChanges(
                    (
                        "services/ari-core/src/ari_core/runtime/loop_runner.py",
                        "tests/unit/test_runtime_loop_runner.py",
                    )
                ),
            ],
        ),
    }


def _build_profile_from_slice(slice_spec) -> VerificationProfile:
    checks: list[Check] = []
    for path in slice_spec.expected_paths:
        checks.append(FileChanged(path))
    for path, symbols in slice_spec.expected_symbols.items():
        for symbol in symbols:
            checks.append(SymbolExists(path, symbol))
    for command in getattr(slice_spec, "verification_commands", ()):
        checks.append(
            OptionalCustomCheck(
                "command_succeeds",
                {
                    "command": list(command),
                    "description": "legacy verification command succeeded",
                },
            )
        )
    if slice_spec.expected_paths:
        checks.append(NoUnexpectedChanges(tuple(slice_spec.expected_paths)))
    return VerificationProfile(slice_key=slice_spec.key, checks=checks)


def _run_command(command: Sequence[str], repo_root: Path) -> CommandExecutionResult:
    completed = subprocess.run(
        list(command),
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return CommandExecutionResult(
        command=list(command),
        success=completed.returncode == 0,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _command_succeeds_check(context: VerificationContext, config: dict[str, object]) -> VerificationCheckResult:
    raw_command = config.get("command", [])
    command = [str(part) for part in raw_command]
    result = _run_command(command, context.repo_root)
    description = str(config.get("description", f"Command succeeded: {' '.join(command)}"))
    details = description if result.success else result.stderr or result.stdout or "command failed"
    return VerificationCheckResult(
        check_type="OptionalCustomCheck",
        description=description,
        passed=result.success,
        required=bool(config.get("required", False)),
        details=details,
    )


CUSTOM_CHECKS: dict[str, CustomCheckCallable] = {
    "command_succeeds": _command_succeeds_check,
}
