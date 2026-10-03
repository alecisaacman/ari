"""Explicit command capabilities for ARI execution tools.

A command request is never trusted as an executable path or a shell string. It names
a logical capability, and the capability validates the request's shape and builds the
argv itself, starting from an executable at a fixed location that ARI selects. Binary
identity is not cryptographically verified. Anything that is not an explicit
capability is refused.

Classification is about what the *command* can do, not what ARI hopes it does:

- `read_only_inspection` (`ls`, `cat`): system binaries with a fixed option set, and
  every path argument validated to lie within the execution root. Validation is
  path-based; the binary opens the path again later (see the read notes in
  docs/execution/execution-authority.md).
- `code_execution` (`pytest`, `node`): runs local code from the execution root. A test
  file, `conftest.py`, or script can do anything the OS user can. ARI constrains what
  it *requests* (interpreter, options, config overrides, paths, environment); it does
  not contain what the code does. These commands are treated as potentially mutating.

`npm` has no capability: npm scripts are arbitrary package-defined code with their
own configuration and network behaviour, and no narrow form is defined, so it is
refused by default.

Process-group cleanup in `run_prepared_command` is best-effort hygiene only. It is not
evidence that an effect cannot land; `run_command` stays `unbounded` for redispatch.
"""

from __future__ import annotations

import io
import locale
import os
import select
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum, StrEnum
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
        """Validate that `raw` resolves to a path within the execution root (path-based)."""
        if not raw or raw.startswith("-"):
            raise CommandCapabilityError(f"{label} must be a path, not an option: {raw!r}")
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = self.cwd / candidate
        resolved = candidate.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise CommandCapabilityError(f"{label} escapes execution root: {raw}")
        return resolved

    def readable_file(self, raw: str, *, label: str) -> Path:
        """A validated path that is not a symlink or a multiply-linked regular file.

        A hard link is an alias for an inode that may live outside the root, so a
        file with more than one link is refused rather than read.
        """
        if not raw or raw.startswith("-"):
            raise CommandCapabilityError(f"{label} must be a path, not an option: {raw!r}")
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = self.cwd / candidate
        try:
            info = os.lstat(candidate)
        except FileNotFoundError:
            info = None
        if info is not None and stat.S_ISLNK(info.st_mode):
            raise CommandCapabilityError(f"{label} may not be a symlink: {raw}")
        if info is not None and stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
            raise CommandCapabilityError(f"{label} has multiple hard links: {raw}")
        return self.confined_path(raw, label=label)


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
    environment: tuple[tuple[str, str], ...] = ()

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
    environment: tuple[tuple[str, str], ...] = ()

    @property
    def mutating(self) -> bool:
        return self.command_class is CommandClass.CODE_EXECUTION


# --- executables at fixed locations ---------------------------------------------------

SYSTEM_BIN_DIRS = ("/bin", "/usr/bin")
NODE_SEARCH_PATH = os.pathsep.join(("/opt/homebrew/bin", "/usr/local/bin", *SYSTEM_BIN_DIRS))


def _system_binary(name: str) -> str:
    for directory in SYSTEM_BIN_DIRS:
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise CommandCapabilityError(f"System {name} is not available in /bin or /usr/bin.")


def selected_python() -> str:
    """The interpreter running ARI; requested interpreter paths are never executed."""
    return sys.executable


def is_python_spelling(token: str) -> bool:
    """Whether a request token names *a* Python interpreter (mapped to ARI's own)."""
    name = Path(token).name
    version = sys.version_info
    return name in {
        "python",
        f"python{version.major}",
        f"python{version.major}.{version.minor}",
        Path(sys.executable).name,
    }


def _selected_node() -> str:
    node = shutil.which("node", path=NODE_SEARCH_PATH)
    if node is None:
        raise CommandCapabilityError("node is not available in system install locations.")
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
        context.readable_file(path, label="cat path")
    return [_system_binary("cat"), "--", *args]


# --- code execution ----------------------------------------------------------------------

PYTEST_FLAGS = frozenset(
    {"-q", "--quiet", "-v", "--verbose", "-x", "--exitfirst", "-s", "--no-header"}
)
PYTEST_VALUE_OPTIONS = frozenset({"-k", "-m", "--tb", "--maxfail"})
PYTEST_TB_STYLES = frozenset({"auto", "long", "short", "line", "native", "no"})
# Generated by ARI, never accepted from a request. They stop root config from adding
# options the request contract refuses (addopts), importing from outside the root
# (pythonpath), choosing collection roots (testpaths), or writing logs and cache
# files elsewhere (log_file, cacheprovider).
PYTEST_INTERNAL_OPTIONS = (
    "-p",
    "no:cacheprovider",
    "-o",
    "addopts=",
    "-o",
    "pythonpath=",
    "-o",
    "testpaths=",
    "-o",
    "log_file=",
)
PYTEST_ENVIRONMENT = (
    ("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1"),
    ("PYTHONNOUSERSITE", "1"),
)
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
        selected_python(),
        # -P: do not put the cwd (the execution root) on sys.path, so a root-local
        # pytest.py or pytest/ package cannot replace the installed pytest.
        "-P",
        "-m",
        "pytest",
        "-c",
        _pytest_config(context.root),
        "--rootdir",
        root,
        "--confcutdir",
        root,
        *PYTEST_INTERNAL_OPTIONS,
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
        return [_selected_node(), "--check", args[1]]
    if len(args) >= 2 and args[0] == "--test":
        for path in args[1:]:
            context.confined_path(path, label="node --test path")
        return [_selected_node(), "--test", *args[1:]]
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
        executable_identity="ls from /bin or /usr/bin (fixed location, not verified)",
        argv_shape=f"ls [{' '.join(sorted(LS_OPTIONS))}] [path...]",
        path_arguments="every non-option argument; validated path within the execution root",
        match=_exact("ls"),
        build=_build_ls,
    ),
    "cat": CommandCapability(
        name="cat",
        command_class=CommandClass.READ_ONLY_INSPECTION,
        description="Print files inside the execution root.",
        executable_identity="cat from /bin or /usr/bin (fixed location, not verified)",
        argv_shape="cat <path>...",
        path_arguments=(
            "every argument; validated path within the execution root, not a symlink, "
            "not a multiply-linked file"
        ),
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
        executable_identity=(
            "sys.executable -P -m pytest (requested interpreter path ignored; "
            "binary identity not verified)"
        ),
        argv_shape=(
            "pytest|python -m pytest [-q -v -x -s --no-header -k EXPR -m EXPR "
            "--tb=STYLE --maxfail=N] [path[::node]...]"
        ),
        path_arguments="test paths and node ids; validated paths within the execution root",
        match=_match_pytest,
        build=_build_pytest,
        environment=PYTEST_ENVIRONMENT,
    ),
    "node": CommandCapability(
        name="node",
        command_class=CommandClass.CODE_EXECUTION,
        description="Syntax-check or run Node tests for files inside the execution root.",
        executable_identity=(
            "node from fixed install locations, not the caller's PATH; these may be "
            "user-writable and the binary is not verified"
        ),
        argv_shape="node --check <file> | node --test <file>...",
        path_arguments="every file argument; validated path within the execution root",
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
    """Resolve a request to exactly one capability and build its argv."""
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
            environment=capability.environment,
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
    env.update(dict(prepared.environment))
    for name in STRIPPED_ENVIRONMENT:
        env.pop(name, None)
    return env


def _scratch_dirs(root: Path) -> tuple[Path, Path]:
    """Create `<root>/.ari-exec/{home,tmp}` relative to directory descriptors.

    Every component is created or opened with `O_NOFOLLOW` relative to its parent's
    descriptor, so a pre-existing symlink (dangling or not) is refused instead of
    followed out of the root.
    """
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        scratch_fd = _open_private_dir(root_fd, SCRATCH_DIR_NAME)
        try:
            _ensure_regular_file(scratch_fd, ".gitignore", b"*\n")
            for name in ("home", "tmp"):
                os.close(_open_private_dir(scratch_fd, name))
        finally:
            os.close(scratch_fd)
    finally:
        os.close(root_fd)
    scratch = root / SCRATCH_DIR_NAME
    return scratch / "home", scratch / "tmp"


def _open_private_dir(parent_fd: int, name: str) -> int:
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    try:
        return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except OSError as error:  # ELOOP for a symlink, ENOTDIR for a non-directory
        raise CommandCapabilityError(
            f"Command scratch path {name!r} is not a real directory inside the root."
        ) from error


def _ensure_regular_file(dir_fd: int, name: str, content: bytes) -> None:
    try:
        fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o644,
            dir_fd=dir_fd,
        )
    except FileExistsError:
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise CommandCapabilityError(
                f"Command scratch file {name!r} is not a regular file."
            ) from None
        return
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)


TERMINATE_GRACE_SECONDS = 2.0


class _LeaderState(Enum):
    RUNNING = "running"
    EXITED_UNREAPED = "exited_unreaped"
    UNKNOWN = "unknown"


def run_prepared_command(
    prepared: PreparedCommand,
    *,
    timeout_seconds: float,
    pass_fds: Sequence[int] = (),
) -> subprocess.CompletedProcess[str]:
    """Run a prepared command as the leader of a new process group.

    Ownership rule: ARI signals the group only while it has *not yet reaped* the
    leader. An unreaped leader, running or a zombie, keeps its PID and therefore the
    group ID reserved, so the signal cannot reach an unrelated group that reused the
    number.

    - Timeout (leader still running at the deadline): SIGTERM the group, wait up to a
      grace period, SIGKILL the group, reap, raise `TimeoutExpired`.
    - Normal return: ARI waits for the leader to exit *without reaping it* (kqueue
      on macOS, `waitid(WNOWAIT)` where available), SIGKILLs any remaining group
      members, then reaps. Where neither primitive exists, it reaps without the
      post-return cleanup rather than risk signalling a reused group ID.

    None of this proves an effect did not land. A descendant that calls `setsid` or
    daemonizes leaves the group, and code in the ARI process that reaps arbitrary
    children (`waitpid(-1)`) would break the ownership rule.
    """
    argv = list(prepared.argv)
    process = subprocess.Popen(
        argv,
        cwd=str(prepared.cwd),
        env=command_environment(prepared),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        pass_fds=tuple(pass_fds),
    )
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout_seconds
    try:
        pipes_closed = _drain(process, output, deadline)
        remaining = max(0.0, deadline - time.monotonic()) if pipes_closed else 0.0
        state = _wait_for_exit_unreaped(process.pid, remaining)
        if state is _LeaderState.RUNNING or (
            state is _LeaderState.UNKNOWN and not pipes_closed
        ):
            _terminate_group(process, output)
            process.wait()
            raise subprocess.TimeoutExpired(
                argv,
                timeout_seconds,
                output=_decode(output["stdout"]),
                stderr=_decode(output["stderr"]),
            )
        if state is _LeaderState.EXITED_UNREAPED:
            _signal_group(process, signal.SIGKILL)  # best-effort: remaining members
            if not pipes_closed:
                _drain(process, output, time.monotonic() + TERMINATE_GRACE_SECONDS)
            process.wait()
        else:
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                _terminate_group(process, output)  # still unreaped, so still ours
                process.wait()
                raise subprocess.TimeoutExpired(
                    argv,
                    timeout_seconds,
                    output=_decode(output["stdout"]),
                    stderr=_decode(output["stderr"]),
                ) from None
    finally:
        if process.returncode is None:
            _signal_group(process, signal.SIGKILL)
            process.wait()
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
    return subprocess.CompletedProcess(
        argv, process.returncode, _decode(output["stdout"]), _decode(output["stderr"])
    )


def _terminate_group(
    process: subprocess.Popen[bytes],
    output: dict[str, bytearray],
) -> None:
    _signal_group(process, signal.SIGTERM)
    if _wait_for_exit_unreaped(process.pid, TERMINATE_GRACE_SECONDS) is _LeaderState.UNKNOWN:
        _drain(process, output, time.monotonic() + TERMINATE_GRACE_SECONDS)
    _signal_group(process, signal.SIGKILL)
    _drain(process, output, time.monotonic() + TERMINATE_GRACE_SECONDS)


def _drain(
    process: subprocess.Popen[bytes],
    output: dict[str, bytearray],
    deadline: float,
) -> bool:
    """Read stdout/stderr until both reach EOF (True) or the deadline passes (False)."""
    streams = {"stdout": process.stdout, "stderr": process.stderr}
    with selectors.DefaultSelector() as selector:
        for name, stream in streams.items():
            if stream is not None and not stream.closed:
                selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fd, 65536)
                if chunk:
                    output[key.data].extend(chunk)
                else:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()  # type: ignore[union-attr]
    return True


def _wait_for_exit_unreaped(pid: int, timeout: float) -> _LeaderState:
    """Wait up to `timeout` for `pid` to exit without reaping it."""
    if hasattr(os, "waitid"):
        end = time.monotonic() + max(timeout, 0.0)
        while True:
            try:
                info = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
            except ChildProcessError:
                return _LeaderState.UNKNOWN
            if info is not None:
                return _LeaderState.EXITED_UNREAPED
            if time.monotonic() >= end:
                return _LeaderState.RUNNING
            time.sleep(0.01)
    if hasattr(select, "kqueue"):
        queue = select.kqueue()
        try:
            event = select.kevent(
                pid,
                filter=select.KQ_FILTER_PROC,
                flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                fflags=select.KQ_NOTE_EXIT,
            )
            try:
                events = queue.control([event], 1, max(timeout, 0.0))
            except OSError:
                return _LeaderState.UNKNOWN
            return _LeaderState.EXITED_UNREAPED if events else _LeaderState.RUNNING
        finally:
            queue.close()
    return _LeaderState.UNKNOWN


def _signal_group(process: subprocess.Popen[bytes], sig: signal.Signals) -> None:
    if process.returncode is not None:
        raise RuntimeError("Refusing to signal the process group of an already-reaped leader.")
    pgid = process.pid
    if pgid <= 1 or pgid == os.getpgrp():
        return
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _decode(data: bytes | bytearray) -> str:
    encoding = locale.getpreferredencoding(False)
    return io.TextIOWrapper(io.BytesIO(bytes(data)), encoding=encoding, errors="replace").read()
