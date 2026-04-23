from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from .verification_profiles import (
    FileChanged,
    NoUnexpectedChanges,
    OutputMatches,
    SymbolExists,
    TestPasses,
    VerificationProfile,
)

if TYPE_CHECKING:
    from .self_improvement_runner import SelfImprovementCycle, SliceSelection


@dataclass(frozen=True, slots=True)
class ActionPlan:
    slice_key: str
    milestone: str
    attempt_kind: str
    task_description: str
    constraints: list[str]
    likely_files: list[str]
    expected_symbols: dict[str, list[str]]
    verification_expectations: list[str]
    retry_refinement_hints: list[str]
    failed_checks: list[str]
    prompt_text: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_action_plan(
    *,
    goal: str,
    selection: SliceSelection,
    verification_profile: VerificationProfile,
    previous_cycle: SelfImprovementCycle | None = None,
) -> ActionPlan:
    slice_spec = selection.slice_spec
    likely_files = _likely_files_for_profile(slice_spec, verification_profile)
    expected_symbols = _expected_symbols_for_profile(slice_spec, verification_profile)
    verification_expectations = _verification_expectations_for_profile(verification_profile)
    attempt_kind = "retry" if previous_cycle is not None else "initial"
    failed_checks = [] if previous_cycle is None else [check.details for check in previous_cycle.verification_result.failed_checks]
    retry_refinement_hints = _retry_hints(slice_spec, previous_cycle)
    constraints = [
        "Keep the change local, bounded, and testable.",
        "Preserve ARI as controller and Codex as worker.",
        "Do not widen shell access, autonomy, or architecture scope.",
        "Prefer the likely files first; only touch adjacent files when required to complete verification cleanly.",
    ]
    task_description = f"{slice_spec.title}. {slice_spec.prompt_hint}".strip()
    prompt_text = render_worker_prompt(
        goal=goal,
        selection=selection,
        task_description=task_description,
        constraints=constraints,
        likely_files=likely_files,
        expected_symbols=expected_symbols,
        verification_expectations=verification_expectations,
        retry_refinement_hints=retry_refinement_hints,
        failed_checks=failed_checks,
        attempt_kind=attempt_kind,
    )
    return ActionPlan(
        slice_key=slice_spec.key,
        milestone=slice_spec.milestone,
        attempt_kind=attempt_kind,
        task_description=task_description,
        constraints=constraints,
        likely_files=likely_files,
        expected_symbols=expected_symbols,
        verification_expectations=verification_expectations,
        retry_refinement_hints=retry_refinement_hints,
        failed_checks=failed_checks,
        prompt_text=prompt_text,
    )


def render_worker_prompt(
    *,
    goal: str,
    selection: SliceSelection,
    task_description: str,
    constraints: list[str],
    likely_files: list[str],
    expected_symbols: dict[str, list[str]],
    verification_expectations: list[str],
    retry_refinement_hints: list[str],
    failed_checks: list[str],
    attempt_kind: str,
) -> str:
    lines: list[str] = [
        "You are Codex, acting as a bounded coding worker under ARI's control.",
        f"High-level goal: {goal}",
        f"Slice key: {selection.slice_spec.key}",
        f"Milestone: {selection.slice_spec.milestone}",
        f"Attempt: {attempt_kind}",
        "",
        "Concrete task:",
        f"- {task_description}",
        "",
        "Why ARI chose this slice:",
        f"- {selection.reason}",
    ]

    if likely_files:
        lines.extend(["", "Likely files to inspect or change:"])
        lines.extend(f"- {path}" for path in likely_files)

    if expected_symbols:
        lines.extend(["", "Expected symbols or structural targets:"])
        for path, symbols in expected_symbols.items():
            lines.append(f"- {path}: {', '.join(symbols)}")

    if verification_expectations:
        lines.extend(["", "Success looks like:"])
        lines.extend(f"- {expectation}" for expectation in verification_expectations)

    lines.extend(["", "Constraints:"])
    lines.extend(f"- {constraint}" for constraint in constraints)

    if failed_checks:
        lines.extend(["", "Previous verification gaps:"])
        lines.extend(f"- {detail}" for detail in failed_checks)

    if retry_refinement_hints:
        lines.extend(["", "Retry refinement guidance:"])
        lines.extend(f"- {hint}" for hint in retry_refinement_hints)

    lines.extend(
        [
            "",
            "Deliverable:",
            "- Make the smallest coherent change that completes this slice.",
            "- Report files changed, verification you ran, and any remaining risk.",
        ]
    )
    return "\n".join(lines)


def _likely_files_for_profile(slice_spec, verification_profile: VerificationProfile) -> list[str]:
    files: list[str] = list(slice_spec.expected_paths)
    for check in verification_profile.checks:
        if isinstance(check, (FileChanged, SymbolExists, TestPasses)):
            path = check.path
            if path not in files:
                files.append(path)
        if isinstance(check, NoUnexpectedChanges):
            for path in check.allowed_paths:
                if path not in files:
                    files.append(path)
    return files


def _expected_symbols_for_profile(slice_spec, verification_profile: VerificationProfile) -> dict[str, list[str]]:
    symbols: dict[str, list[str]] = {path: list(names) for path, names in slice_spec.expected_symbols.items()}
    for check in verification_profile.checks:
        if isinstance(check, SymbolExists):
            symbols.setdefault(check.path, [])
            if check.name not in symbols[check.path]:
                symbols[check.path].append(check.name)
    return symbols


def _verification_expectations_for_profile(verification_profile: VerificationProfile) -> list[str]:
    expectations: list[str] = []
    for check in verification_profile.checks:
        if isinstance(check, FileChanged):
            expectations.append(f"{check.path} changes in the current slice.")
        elif isinstance(check, SymbolExists):
            expectations.append(f"{check.name} is present in {check.path}.")
        elif isinstance(check, TestPasses):
            expectations.append(f"{check.path} passes.")
        elif isinstance(check, OutputMatches):
            expectations.append(f"worker output matches '{check.pattern}'.")
        elif isinstance(check, NoUnexpectedChanges):
            expectations.append("no unexpected changed paths are introduced.")
        else:
            expectations.append(check.__class__.__name__)
    return expectations


def _retry_hints(slice_spec, previous_cycle: SelfImprovementCycle | None) -> list[str]:
    if previous_cycle is None:
        return [
            "Do not widen the slice beyond the bounded milestone.",
            "Do not retry blindly; verify the targeted files and symbols before finishing.",
        ]

    hints = [
        "Address the failed semantic checks directly before changing anything else.",
        "Do not repeat the same unsupported approach if the failed checks remain unaddressed.",
    ]
    for failed in previous_cycle.verification_result.failed_checks:
        hints.append(f"Specifically resolve: {failed.details}")
    if previous_cycle.repo_inspection.newly_changed_paths:
        hints.append(
            "Keep the retry focused; avoid expanding beyond the files already implicated unless a directly supporting test file is necessary."
        )
    return hints
