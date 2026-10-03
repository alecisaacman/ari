"""Explicit command capabilities for ARI execution tools.

A command request is never trusted as an executable path or a shell string. It names
a logical capability, and the capability validates the request's shape and builds the
argv itself, starting from a trusted executable. Anything that is not an explicit
capability is refused.

Classification is about what the *command* can do, not what ARI hopes it does:

- `read_only_inspection` (`ls`, `cat`): fixed system binaries with a fixed option set
  and every path argument confined to the execution root.
- `code_execution` (`pytest`, `node`): runs local code from the execution root. A test
  file, `conftest.py`, or script can do anything the OS user can. ARI constrains what
  it *requests* (interpreter, options, paths, environment); it does not contain what
  the code does. These commands are treated as potentially mutating.

`npm` has no capability: npm scripts are arbitrary package-defined code with their
own configuration and network behaviour, and no narrow form is defined, so it is
refused by default.

Process-group cleanup in `run_prepared_command` is best-effort hygiene only. It is not
evidence that an effect cannot land; `run_command` stays `unbounded` for redispatch.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class CommandClass(StrEnum):
    READ_ONLY_INSPECTION = "read_only_inspection"
    CODE_EXECUTION = "code_execution"


class CommandCapabilityError(ValueError):
    """A command request does not match an explicit ARI command capability."""


@dataclass(frozen=True, slots=True)
class CommandContext:
    root: Path
    cwd: Path

    def confined_path(self, raw: str, *, label: str) -> Path:
        if not raw or raw.startswith("-"):
            raise CommandCapabilityError(f"{label} must be a path, not an option: {raw!r}")
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = self.cwd / candidate
        resolved = candidate.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise CommandCapabilityError(f"{label} escapes execution root: {raw}")
        return resolved


Matcher = Callable[[Sequence[str]], list[str] | None]
Builder = Callable[[list[str], CommandContext], list[str]]


@dataclass(frozen=True, slots=True)
class CommandCapability:
    name: str
    command_class: CommandClass
    description: str
    executable_identity: str
    argv_shape: str
    path_arguments: str
    match: Matcher
    build: Builder

    @property
    def mutating(self) -> bool:
        return self.command_class is CommandClass.CODE_EXECUTION

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "classification": str(self.command_class),
            "mutating": self.mutating,
            "description": self.description,
            "executable_identity": self.executable_identity,
            "argv_shape": self.argv_shape,
            "path_arguments": self.path_arguments,
        }


@dataclass(frozen=True, slots=True)
class PreparedCommand:
    capability: str
    command_class: CommandClass
    argv: tuple[str, ...]
    cwd: Path
    root: Path

    @property
    def mutating(self) -> bool:
        return self.command_class is CommandClass.CODE_EXECUTION


# --- trusted executables ---------------------------------------------------------------

SYSTEM_BIN_DIRS = ("/bin", "/usr/bin")
NODE_SEARCH_PATH = os.pathsep.join(("/opt/homebrew/bin", "/usr/local/bin", *SYSTEM_BIN_DIRS))


def _system_binary(name: str) -> str:
    for directory in SYSTEM_BIN_DIRS:
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise CommandCapabilityError(f"Trusted system {name} is not available.")


def trusted_python() -> str:
    """The interpreter running ARI; requested interpreter paths are never executed."""
    return sys.executable


def is_python_spelling(token: str) -> bool:
    """Whether a request token names *a* Python interpreter (mapped to the trusted one)."""
    name = Path(token).name
    version = sys.version_info
    return name in {
        "python",
        f"python{version.major}",
        f"python{version.major}.{version.minor}",
        Path(sys.executable).name,
    }


def _trusted_node() -> str:
    node = shutil.which("node", path=NODE_SEARCH_PATH)
    if node is None:
        raise CommandCapabilityError("Trusted node is not available in system locations.")
    return node


# --- read-only inspection ----------------------------------------------------------------

LS_OPTIONS = frozenset({"-1", "-a", "-A", "-l", "-la", "-al", "-lA", "-Al", "-F"})


def _build_ls(args: list[str], context: CommandContext) -> list[str]:
    options = [arg for arg in args if arg.startswith("-")]
    for option in options:
        if option not in LS_OPTIONS:
            raise CommandCapabilityError(f"ls option is not permitted: {option}")
    paths = [arg for arg in args if not arg.startswith("-")]
    for path in paths:
        context.confined_path(path, label="ls path")
    return [_system_binary("ls"), *options, "--", *paths]


def _build_cat(args: list[str], context: CommandContext) -> list[str]:
    if not args:
        raise CommandCapabilityError("cat requires at least one path.")
    for path in args:
        context.confined_path(path, label="cat path")
    return [_system_binary("cat"), "--", *args]


# --- code execution ----------------------------------------------------------------------

PYTEST_FLAGS = frozenset(
    {"-q", "--quiet", "-v", "--verbose", "-x", "--exitfirst", "-s", "--no-header"}
)
PYTEST_VALUE_OPTIONS = frozenset({"-k", "-m", "--tb", "--maxfail"})
PYTEST_TB_STYLES = frozenset({"auto", "long", "short", "line", "native", "no"})
PYTEST_CONFIG_FILES = (
    ("pytest.ini", None),
    (".pytest.ini", None),
    ("pyproject.toml", "[tool.pytest"),
    ("tox.ini", "[pytest]"),
    ("setup.cfg", "[tool:pytest]"),
)


def _pytest_config(root: Path) -> str:
    """Pin pytest's config to the root so files above it cannot inject options."""
    for name, marker in PYTEST_CONFIG_FILES:
        candidate = root / name
        if not candidate.is_file():
            continue
        if marker is None or marker in candidate.read_text(encoding="utf-8", errors="replace"):
            return str(candidate)
    return os.devnull


def _build_pytest(args: list[str], context: CommandContext) -> list[str]:
    validated: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in PYTEST_FLAGS:
            validated.append(arg)
        elif arg.startswith("-"):
            option, has_inline_value, inline_value = arg.partition("=")
            if option not in PYTEST_VALUE_OPTIONS or (option in {"-k", "-m"} and has_inline_value):
                raise CommandCapabilityError(f"pytest option is not permitted: {arg}")
            if has_inline_value:
                value = inline_value
            else:
                index += 1
                if index >= len(args):
                    raise CommandCapabilityError(f"pytest option {option} requires a value.")
                value = args[index]
            _check_pytest_value(option, value)
            validated.extend([option, value])
        else:
            if arg.startswith("@"):
                raise CommandCapabilityError(f"pytest argument files are not permitted: {arg}")
            context.confined_path(arg.split("::", 1)[0], label="pytest path")
            validated.append(arg)
        index += 1
    root = str(context.root)
    return [
        trusted_python(),
        "-m",
        "pytest",
        "-c",
        _pytest_config(context.root),
        "--rootdir",
        root,
        "--confcutdir",
        root,
        *validated,
    ]


def _check_pytest_value(option: str, value: str) -> None:
    if not value or value.startswith("-"):
        raise CommandCapabilityError(f"pytest option {option} has an invalid value: {value!r}")
    if option == "--tb" and value not in PYTEST_TB_STYLES:
        raise CommandCapabilityError(f"pytest --tb style is not permitted: {value}")
    if option == "--maxfail" and not (value.isdigit() and int(value) >= 1):
        raise CommandCapabilityError(f"pytest --maxfail must be a positive integer: {value}")


def _match_pytest(command: Sequence[str]) -> list[str] | None:
    if command[0] == "pytest":
        return list(command[1:])
    if len(command) >= 3 and is_python_spelling(command[0]) and list(command[1:3]) == [
        "-m",
        "pytest",
    ]:
        return list(command[3:])
    return None


def _build_node(args: list[str], context: CommandContext) -> list[str]:
    if len(args) == 2 and args[0] == "--check":
        context.confined_path(args[1], label="node --check path")
        return [_trusted_node(), "--check", args[1]]
    if len(args) >= 2 and args[0] == "--test":
        for path in args[1:]:
            context.confined_path(path, label="node --test path")
        return [_trusted_node(), "--test", *args[1:]]
    raise CommandCapabilityError(
        "node is limited to `node --check <file>` and `node --test <file>...`."
    )


def _exact(name: str) -> Matcher:
    return lambda command: list(command[1:]) if command[0] == name else None


COMMAND_CAPABILITIES: dict[str, CommandCapability] = {
    "ls": CommandCapability(
        name="ls",
        command_class=CommandClass.READ_ONLY_INSPECTION,
        description="List directories inside the execution root.",
        executable_identity="system ls from /bin or /usr/bin",
        argv_shape=f"ls [{' '.join(sorted(LS_OPTIONS))}] [path...]",
        path_arguments="every non-option argument; confined to the execution root",
        match=_exact("ls"),
        build=_build_ls,
    ),
    "cat": CommandCapability(
        name="cat",
        command_class=CommandClass.READ_ONLY_INSPECTION,
        description="Print files inside the execution root.",
        executable_identity="system cat from /bin or /usr/bin",
        argv_shape="cat <path>...",
        path_arguments="every argument; confined to the execution root",
        match=_exact("cat"),
        build=_build_cat,
    ),
    "pytest": CommandCapability(
        name="pytest",
        command_class=CommandClass.CODE_EXECUTION,
        description=(
            "Run pytest with ARI's own interpreter. Tests and conftest.py are arbitrary "
            "local Python and are not contained."
        ),
        executable_identity="sys.executable -m pytest (requested interpreter path ignored)",
        argv_shape=(
            "pytest|python -m pytest [-q -v -x -s --no-header -k EXPR -m EXPR "
            "--tb=STYLE --maxfail=N] [path[::node]...]"
        ),
        path_arguments="test paths and node ids; confined to the execution root",
        match=_match_pytest,
        build=_build_pytest,
    ),
    "node": CommandCapability(
        name="node",
        command_class=CommandClass.CODE_EXECUTION,
        description="Syntax-check or run Node tests for files inside the execution root.",
        executable_identity="node from system install locations, not the caller's PATH",
        argv_shape="node --check <file> | node --test <file>...",
        path_arguments="every file argument; confined to the execution root",
        match=_exact("node"),
        build=_build_node,
    ),
}


def get_command_capabilities() -> list[CommandCapability]:
    return list(COMMAND_CAPABILITIES.values())


def prepare_command(
    command: Sequence[str],
    *,
    root: Path,
    cwd: Path | None = None,
) -> PreparedCommand:
    """Resolve a request to exactly one capability and build its trusted argv."""
    if not isinstance(command, (list, tuple)) or not command:
        raise CommandCapabilityError("command is required as a non-empty list[str].")
    if not all(isinstance(item, str) for item in command):
        raise CommandCapabilityError("command must be a list of strings.")
    if any("\x00" in item for item in command):
        raise CommandCapabilityError("command arguments may not contain NUL bytes.")
    context = CommandContext(root=root, cwd=cwd or root)
    for capability in COMMAND_CAPABILITIES.values():
        args = capability.match(command)
        if args is None:
            continue
        argv = capability.build(args, context)
        return PreparedCommand(
            capability=capability.name,
            command_class=capability.command_class,
            argv=tuple(argv),
            cwd=context.cwd,
            root=root,
        )
    if command[0] in {"npm", "npx"}:
        raise CommandCapabilityError(
            f"{command[0]} is refused: npm scripts are arbitrary code and no narrow "
            "capability is defined."
        )
    raise CommandCapabilityError(
        f"command is not allowlisted as an ARI command capability: {command[0]}"
    )


def classify_command(command: Sequence[str], *, root: Path) -> CommandClass:
    return prepare_command(command, root=root).command_class


# --- environment and process lifecycle ----------------------------------------------------

STRIPPED_ENVIRONMENT = frozenset(
    {
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONHOME",
        "NODE_OPTIONS",
        "NODE_PATH",
    }
)
LOCALE_VARIABLES = ("LANG", "LC_ALL", "LC_CTYPE")
SCRATCH_DIR_NAME = ".ari-exec"


def command_environment(prepared: PreparedCommand) -> dict[str, str]:
    """A narrow environment built from scratch rather than inherited."""
    path_dirs = list(dict.fromkeys([str(Path(prepared.argv[0]).parent), *SYSTEM_BIN_DIRS]))
    env = {"PATH": os.pathsep.join(path_dirs)}
    for name in LOCALE_VARIABLES:
        if os.environ.get(name):
            env[name] = os.environ[name]
    env.setdefault("LANG", "C.UTF-8")
    if prepared.mutating:
        home, tmp = _scratch_dirs(prepared.root)
        env.update({"HOME": str(home), "TMPDIR": str(tmp), "TMP": str(tmp), "TEMP": str(tmp)})
    for name in STRIPPED_ENVIRONMENT:
        env.pop(name, None)
    return env


def _scratch_dirs(root: Path) -> tuple[Path, Path]:
    scratch = root / SCRATCH_DIR_NAME
    home = scratch / "home"
    tmp = scratch / "tmp"
    for directory in (scratch, home, tmp):
        directory.mkdir(exist_ok=True)
        if directory.is_symlink() or Path(os.path.realpath(directory)) != directory:
            raise CommandCapabilityError(f"Command scratch directory is not confined: {directory}")
    ignore = scratch / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    return home, tmp


TERMINATE_GRACE_SECONDS = 2.0


def run_prepared_command(
    prepared: PreparedCommand,
    *,
    timeout_seconds: float,
    pass_fds: Sequence[int] = (),
) -> subprocess.CompletedProcess[str]:
    """Run a prepared command as the leader of a new process group.

    On timeout the whole group is terminated, then killed, and `TimeoutExpired` is
    raised. After a normal return, remaining group members are killed best-effort.
    Neither step proves an effect did not land: a descendant that started its own
    session or daemonized escapes the group.
    """
    process = subprocess.Popen(
        list(prepared.argv),
        cwd=str(prepared.cwd),
        env=command_environment(prepared),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        pass_fds=tuple(pass_fds),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = process.poll() is None
        _signal_group(process.pid, signal.SIGTERM if timed_out else signal.SIGKILL)
        try:
            stdout, stderr = process.communicate(timeout=TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            _signal_group(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        if timed_out:
            raise subprocess.TimeoutExpired(
                list(prepared.argv), timeout_seconds, output=stdout, stderr=stderr
            ) from None
    finally:
        if process.poll() is None:
            _signal_group(process.pid, signal.SIGKILL)
            process.wait()
    _signal_group(process.pid, signal.SIGKILL)  # best-effort: remaining group members
    return subprocess.CompletedProcess(list(prepared.argv), process.returncode, stdout, stderr)


def _signal_group(pgid: int, sig: signal.Signals) -> None:
    if pgid <= 1 or pgid == os.getpgrp():
        return
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass
