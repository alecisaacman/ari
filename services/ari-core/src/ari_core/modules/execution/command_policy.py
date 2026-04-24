from __future__ import annotations

import shlex
from dataclasses import asdict, dataclass
from pathlib import Path

from ...core.paths import PROJECT_ROOT


@dataclass(frozen=True, slots=True)
class CommandPolicyResult:
    allowed: bool
    command: str
    reason: str
    rejection_code: str | None = None
    normalized_command: str | None = None
    category: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


SHELL_CONTROL_TOKENS = (
    "&&",
    "||",
    "|",
    ";",
    ">>",
    ">",
    "<",
    "`",
    "$(",
    "$",
)

DISALLOWED_EXECUTABLES = {
    "brew",
    "chmod",
    "chown",
    "cp",
    "curl",
    "docker",
    "mv",
    "npm",
    "npx",
    "open",
    "pip",
    "pnpm",
    "rm",
    "rsync",
    "scp",
    "sh",
    "ssh",
    "su",
    "sudo",
    "wget",
    "yarn",
}


def validate_command(command: str, repo_root: Path | None = None) -> CommandPolicyResult:
    root = (repo_root or PROJECT_ROOT).expanduser().resolve()
    raw_command = command.strip()
    if not raw_command:
        return _reject(command, "Command is required.", "empty_command")

    shell_token = _first_shell_control_token(raw_command)
    if shell_token is not None:
        return _reject(
            command,
            f"Shell control token is not allowed: {shell_token}",
            "shell_control_token",
        )

    try:
        tokens = shlex.split(raw_command, posix=True)
    except ValueError as error:
        return _reject(command, f"Command parsing failed: {error}", "parse_error")

    if not tokens:
        return _reject(command, "Command is required.", "empty_command")

    executable = tokens[0]
    if executable in DISALLOWED_EXECUTABLES:
        return _reject(
            command,
            f"Executable is not allowed by verification policy: {executable}",
            "disallowed_executable",
        )

    normalized = shlex.join(tokens)
    result = (
        _validate_pytest(tokens, root, command, normalized)
        or _validate_ruff(tokens, root, command, normalized)
        or _validate_git(tokens, root, command, normalized)
        or _validate_ls(tokens, root, command, normalized)
    )
    if result is not None:
        return result

    return _reject(
        command,
        "Command does not match any safe verification policy.",
        "not_allowlisted",
    )


def _validate_pytest(
    tokens: list[str],
    root: Path,
    command: str,
    normalized: str,
) -> CommandPolicyResult | None:
    prefix = [".venv312/bin/python", "-m", "pytest"]
    if tokens[:3] != prefix:
        return None

    args = tokens[3:]
    if args == ["tests/unit", "-q"]:
        return _allow(command, normalized, "unit_tests", "Allowed full unit test command.")
    if len(args) == 2 and args[1] == "-q":
        test_path = args[0]
        safe_path = _safe_repo_path(test_path, root)
        if safe_path is None:
            return _reject(command, f"Unsafe pytest path: {test_path}", "unsafe_path")
        relative = safe_path.relative_to(root).as_posix()
        if (
            relative.startswith("tests/unit/")
            and relative.endswith(".py")
            and "*" not in relative
        ):
            return _allow(
                command,
                normalized,
                "focused_unit_tests",
                "Allowed focused unit test command.",
            )
        return _reject(command, f"Unsafe pytest target: {test_path}", "unsafe_pytest_target")
    return _reject(command, "Pytest command shape is not allowed.", "unsafe_pytest_shape")


def _validate_ruff(
    tokens: list[str],
    root: Path,
    command: str,
    normalized: str,
) -> CommandPolicyResult | None:
    prefix = [".venv312/bin/python", "-m", "ruff", "check"]
    if tokens[:4] != prefix:
        return None

    paths = tokens[4:]
    if not paths:
        return _reject(command, "Ruff check requires at least one safe path.", "missing_path")
    for path in paths:
        safe_path = _safe_repo_path(path, root)
        if safe_path is None:
            return _reject(command, f"Unsafe ruff path: {path}", "unsafe_path")
        if "*" in path:
            return _reject(command, f"Unsafe wildcard path: {path}", "unsafe_wildcard")
    return _allow(command, normalized, "lint", "Allowed ruff check command.")


def _validate_git(
    tokens: list[str],
    root: Path,
    command: str,
    normalized: str,
) -> CommandPolicyResult | None:
    if tokens[0] != "git":
        return None
    if tokens == ["git", "status", "--short"]:
        return _allow(command, normalized, "git_inspection", "Allowed git status inspection.")
    if tokens == ["git", "diff", "--stat"]:
        return _allow(command, normalized, "git_inspection", "Allowed git diff summary.")
    if len(tokens) == 4 and tokens[:3] == ["git", "diff", "--"]:
        safe_path = _safe_repo_path(tokens[3], root)
        if safe_path is None:
            return _reject(command, f"Unsafe git diff path: {tokens[3]}", "unsafe_path")
        return _allow(command, normalized, "git_inspection", "Allowed git diff path inspection.")
    return _reject(command, "Git command is not allowed by verification policy.", "unsafe_git")


def _validate_ls(
    tokens: list[str],
    root: Path,
    command: str,
    normalized: str,
) -> CommandPolicyResult | None:
    if tokens[0] != "ls":
        return None
    if len(tokens) != 2:
        return _reject(command, "ls must target exactly one safe repo path.", "unsafe_ls_shape")
    safe_path = _safe_repo_path(tokens[1], root)
    if safe_path is None:
        return _reject(command, f"Unsafe ls path: {tokens[1]}", "unsafe_path")
    return _allow(command, normalized, "list", "Allowed read-only listing command.")


def _safe_repo_path(raw_path: str, root: Path) -> Path | None:
    if not raw_path or ".." in Path(raw_path).parts or _has_wildcard(raw_path):
        return None
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        try:
            resolved = candidate.resolve()
        except OSError:
            return None
    else:
        resolved = (root / candidate).resolve()
    if resolved == root or root in resolved.parents:
        return resolved
    return None


def _first_shell_control_token(command: str) -> str | None:
    for token in SHELL_CONTROL_TOKENS:
        if token in command:
            return token
    return None


def _has_wildcard(raw_path: str) -> bool:
    return any(token in raw_path for token in ("*", "?", "[", "]"))


def _allow(
    command: str,
    normalized_command: str,
    category: str,
    reason: str,
) -> CommandPolicyResult:
    return CommandPolicyResult(
        allowed=True,
        command=command,
        reason=reason,
        normalized_command=normalized_command,
        category=category,
    )


def _reject(command: str, reason: str, rejection_code: str) -> CommandPolicyResult:
    return CommandPolicyResult(
        allowed=False,
        command=command,
        reason=reason,
        rejection_code=rejection_code,
    )
