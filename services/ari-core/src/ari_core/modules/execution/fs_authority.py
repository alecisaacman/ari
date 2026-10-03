"""Filesystem authority for ARI execution tools.

This module decides *where* execution tools may operate. It is an authority check,
not OS containment: code that ARI runs (for example a test suite) is not confined by
anything here.

- The configured execution root comes from `ARI_EXECUTION_ROOT`, otherwise the
  project root. It may not be `/` and may not overlap ARI's own state storage.
- No execution root may overlap ARI's live runtime: the source checkout it runs from
  and its Python environment (`sys.prefix`, `sys.base_prefix`). Because the fallback
  root *is* the live checkout, an unset `ARI_EXECUTION_ROOT` fails closed. Only the
  operator environment variable `ARI_ALLOW_SELF_MODIFICATION=1` lifts this rule, for
  deliberate ARI self-development; no request parameter can set it. Even then the
  Python environment, `.git`, migrations, schema, and state stay protected paths.
- A requested root (API, CLI, or direct `ExecutionRoot`) must resolve, after symlinks,
  to the configured root or a descendant of it, and must not overlap ARI state.
- Mutating tools may not write beneath protected internal paths: the migration
  directory, the schema file, any `.git` directory, or ARI state storage.
- File replacement never writes through a symlink or into a multiply-linked inode.
  It writes a same-directory temporary file and atomically renames it into place.

Residual risk: parent-directory confinement is revalidated immediately before the
rename, but without `openat`-style directory handles a concurrent local process
that can swap a parent directory for a symlink between that check and `os.replace`
could still redirect the rename. Closing that window needs descriptor-relative
operations or OS-level isolation, which are out of scope here.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from uuid import uuid4

from ...core import paths as core_paths

# Paths relative to any execution root that execution tools must never mutate.
PROTECTED_RELATIVE_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("config", "migrations"),
    ("config", "schema.sql"),
)
PROTECTED_COMPONENT = ".git"
SELF_MODIFICATION_ENV = "ARI_ALLOW_SELF_MODIFICATION"


def state_storage_paths() -> tuple[Path, ...]:
    """ARI's own state and database storage for this process."""
    return tuple(
        dict.fromkeys(
            path.expanduser().resolve()
            for path in (core_paths.ARI_ROOT, core_paths.DB_PATH.parent)
        )
    )


def python_environment_paths() -> tuple[Path, ...]:
    """The interpreter environment ARI runs in (virtualenv and base installation)."""
    return tuple(
        dict.fromkeys(
            Path(path).expanduser().resolve()
            for path in (sys.prefix, sys.exec_prefix, sys.base_prefix)
        )
    )


def live_runtime_paths() -> tuple[Path, ...]:
    """ARI's own running code: its source checkout and its Python environment."""
    return tuple(
        dict.fromkeys((core_paths.PROJECT_ROOT.resolve(), *python_environment_paths()))
    )


def self_modification_allowed() -> bool:
    """Operator-only override; read from ARI's own environment, never from a request."""
    return os.environ.get(SELF_MODIFICATION_ENV) == "1"


def protected_absolute_paths() -> tuple[Path, ...]:
    """Absolute ARI paths that execution tools must never mutate."""
    return tuple(
        dict.fromkeys(
            path.expanduser().resolve()
            for path in (
                core_paths.MIGRATIONS_DIR,
                core_paths.SCHEMA_PATH,
                core_paths.PROJECT_ROOT / PROTECTED_COMPONENT,
                core_paths.LEGACY_STATE_DIR,
                *state_storage_paths(),
                *python_environment_paths(),
            )
        )
    )


def configured_execution_root() -> Path:
    """The server-controlled execution root; no caller input can widen it."""
    env_root = os.environ.get("ARI_EXECUTION_ROOT")
    base = Path(env_root) if env_root else core_paths.PROJECT_ROOT
    root = base.expanduser().resolve()
    if root == Path(root.anchor):
        raise ValueError("The configured execution root may not be the filesystem root.")
    _reject_state_overlap(root, label="configured execution root")
    if not env_root and not self_modification_allowed():
        raise ValueError(
            "ARI_EXECUTION_ROOT is not set, and the fallback execution root is ARI's own "
            f"live checkout ({root}). Set ARI_EXECUTION_ROOT to a separate workspace, or "
            f"set {SELF_MODIFICATION_ENV}=1 to deliberately let ARI modify itself."
        )
    _reject_runtime_overlap(root, label="configured execution root")
    return root


def resolve_execution_root(requested: Path | str | None = None) -> Path:
    """Resolve a requested root, refusing anything outside the configured root."""
    configured = configured_execution_root()
    if requested is None or not str(requested).strip():
        return configured
    candidate = Path(requested).expanduser()
    if not candidate.is_absolute():
        candidate = configured / candidate
    resolved = candidate.resolve()
    if not _is_within(resolved, configured):
        raise ValueError(
            f"Requested execution root is outside the configured execution root: {requested}"
        )
    _reject_state_overlap(resolved, label="requested execution root")
    _reject_runtime_overlap(resolved, label="requested execution root")
    return resolved


def reject_final_symlink(root: Path, raw_path: str | Path) -> None:
    """Refuse a mutation whose requested path names a symlink.

    Resolution would silently redirect the write to the link's target, so the
    unresolved request is checked before it is resolved.
    """
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    if os.path.islink(candidate):
        raise ValueError(f"Execution tools do not write through symlinks: {raw_path}")


def protected_write_reason(root: Path, target: Path) -> str | None:
    """Explain why `target` (resolved and validated within `root`) is protected."""
    relative = tuple(part.casefold() for part in target.relative_to(root).parts)
    if PROTECTED_COMPONENT in relative:
        return f"Execution tools may not modify .git internals: {target}"
    for prefix in PROTECTED_RELATIVE_PREFIXES:
        if relative[: len(prefix)] == prefix:
            return f"Execution tools may not modify ARI migration or schema files: {target}"
    if any(part.casefold() == PROTECTED_COMPONENT for part in target.parts):
        return f"Execution tools may not modify .git internals: {target}"

    folded_target = str(target).casefold()
    protected = protected_absolute_paths()
    for path in protected:
        folded = str(path).casefold()
        if folded_target == folded or folded_target.startswith(folded.rstrip(os.sep) + os.sep):
            return f"Execution tools may not modify protected ARI path: {path}"

    # Identity check catches aliases the string comparison cannot (case, mounts).
    protected_ids = {_identity(path) for path in protected} - {None}
    for ancestor in (target, *target.parents):
        if _identity(ancestor) in protected_ids:
            return f"Execution tools may not modify protected ARI path: {ancestor}"
    return None


def read_text_nofollow(path: Path) -> str:
    """Read a regular file without following a symlink at the final component.

    Path validation cannot prove which inode a path names: a hard link inside the
    root can alias a file outside it. A file with more than one link is refused.
    Intermediate directories are still resolved by path (see the module notes).
    """
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"Execution tools only read regular files: {path}")
        if info.st_nlink > 1:
            raise ValueError(f"Execution tools do not read files with multiple hard links: {path}")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(fd)


def replace_text_atomically(root: Path, target: Path, content: str) -> Path:
    """Replace `target` with `content` via a same-directory temp file and `os.replace`.

    Refuses to write through a symlink or into an inode with other hard links, keeps
    an existing file's permission bits, and revalidates confinement just before the
    rename.
    """
    existing_mode = _check_replaceable(target)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    _check_parent_confined(root, parent)

    # O_EXCL at 0o666 lets the kernel apply the umask to new files, as a plain
    # write would; an existing file keeps its own permission bits.
    temp_path = parent / f".ari-replace-{uuid4().hex}.tmp"
    fd = os.open(
        temp_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o666,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            if existing_mode is not None:
                os.fchmod(handle.fileno(), existing_mode)
            os.fsync(handle.fileno())
        _check_parent_confined(root, parent)
        _check_replaceable(target)
        os.replace(temp_path, target)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return target


def _check_replaceable(target: Path) -> int | None:
    try:
        info = os.lstat(target)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"Execution tools do not write through symlinks: {target}")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Execution tools only replace regular files: {target}")
    if info.st_nlink > 1:
        raise ValueError(f"Execution tools do not replace files with multiple hard links: {target}")
    return stat.S_IMODE(info.st_mode)


def _check_parent_confined(root: Path, parent: Path) -> None:
    real_parent = Path(os.path.realpath(parent))
    if real_parent != parent or not _is_within(real_parent, root):
        raise ValueError(f"Target directory moved outside the execution root: {parent}")


def _reject_state_overlap(root: Path, *, label: str) -> None:
    for state_path in state_storage_paths():
        if _is_within(root, state_path) or _is_within(state_path, root):
            raise ValueError(f"The {label} may not be or contain ARI state storage: {root}")


def _reject_runtime_overlap(root: Path, *, label: str) -> None:
    if self_modification_allowed():
        return
    for runtime_path in live_runtime_paths():
        if _is_within(root, runtime_path) or _is_within(runtime_path, root):
            raise ValueError(
                f"The {label} overlaps ARI's live runtime ({runtime_path}): ARI tools must "
                f"not modify the code or Python environment they run from. Use a separate "
                f"workspace, or set {SELF_MODIFICATION_ENV}=1 for deliberate self-development."
            )


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _identity(path: Path) -> tuple[int, int] | None:
    try:
        info = os.stat(path)
    except OSError:
        return None
    return info.st_dev, info.st_ino
