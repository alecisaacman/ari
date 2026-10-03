"""Hardened runner for ARI's internal, read-only Git inspection commands.

ARI inspects repositories it does not control: an execution root may contain a
`.git` directory that earlier code execution (a test suite, a script) or the
repository's origin has configured. Several Git settings make Git run programs
named in that configuration, for example `core.fsmonitor`, hooks, clean filters
selected by attributes, textconv and external diff drivers, and signature
verification. Run with ARI's own environment, those programs would inherit ARI's
secrets.

`run_git_inspection` supports exactly these subcommands, used for inspection only:
`status`, `branch`, `diff`, `log`, and `hash-object`/`config` internally. For each
call it:

- builds the environment from scratch (no `GIT_DIR`, `GIT_CONFIG_PARAMETERS`,
  `GIT_EXEC_PATH`, `GIT_SSH*`, or any other ambient variable is inherited)
- ignores global and system Git config and attributes
- sets `GIT_OPTIONAL_LOCKS=0`, so status does not write the index or run
  index-change hooks
- disables `core.fsmonitor`, points `core.hooksPath` at /dev/null, empties
  `diff.external`, and turns signature display off
- reads attributes from the empty tree instead of the worktree, and blanks the
  commands of every filter and diff driver defined in the repository's config, so
  `.gitattributes` and `.git/info/attributes` cannot select a program
- passes `--no-ext-diff --no-textconv` to diff/log and ignores submodules
- never uses a shell and always applies a timeout

This hardens only these inspection commands. It does not make arbitrary Git
operations on an untrusted repository safe. It also does not stop
`core.worktree` from pointing inspection at a directory outside the root.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

GIT_SEARCH_PATH = os.pathsep.join(("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"))

# Flags ARI inserts after the subcommand; callers cannot drop them.
SUBCOMMAND_FLAGS: dict[str, tuple[str, ...]] = {
    "status": ("--ignore-submodules=all",),
    "branch": (),
    "diff": ("--no-ext-diff", "--no-textconv", "--ignore-submodules=all"),
    "log": ("--no-ext-diff", "--no-textconv", "--no-show-signature"),
}

# Repository config that would otherwise make these commands run a program.
NEUTRALIZED_CONFIG: tuple[tuple[str, str], ...] = (
    ("core.fsmonitor", "false"),
    ("core.hooksPath", os.devnull),
    ("core.attributesFile", os.devnull),
    ("diff.external", ""),
    ("core.pager", "cat"),
    ("log.showSignature", "false"),
)
DRIVER_COMMANDS = {"filter": ("clean", "smudge", "process"), "diff": ("command", "textconv")}
_DRIVER_KEY = re.compile(r"^(filter|diff)\.(.+)\.(clean|smudge|process|command|textconv)$", re.S)


def git_executable() -> str:
    """Git from fixed install locations; not the caller's PATH. Identity is not verified."""
    git = shutil.which("git", path=GIT_SEARCH_PATH)
    if git is None:
        raise FileNotFoundError("git is not available in system install locations.")
    return git


def run_git_inspection(
    args: Sequence[str],
    cwd: Path | str,
    *,
    timeout: float = 10.0,
) -> subprocess.CompletedProcess[str]:
    """Run one read-only inspection subcommand (`args[0]`) with neutralized config."""
    if not args or args[0] not in SUBCOMMAND_FLAGS:
        raise ValueError(f"Unsupported internal git inspection: {list(args)[:1]}")
    git = git_executable()
    workdir = str(cwd)
    base = _base_environment(git)
    overrides = [*NEUTRALIZED_CONFIG, *_driver_overrides(git, workdir, base, timeout)]
    empty_tree = _empty_tree(git, workdir, base, timeout)
    if empty_tree is None:
        return subprocess.CompletedProcess(
            [git, *args], 128, "", "git could not compute the empty tree for --attr-source."
        )
    argv = [
        git,
        "--no-pager",
        f"--attr-source={empty_tree}",
        args[0],
        *SUBCOMMAND_FLAGS[args[0]],
        *args[1:],
    ]
    return subprocess.run(
        argv,
        cwd=workdir,
        env={**base, **_config_environment(overrides)},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def git_inspection_environment(git: str | None = None) -> dict[str, str]:
    """The complete environment for an inspection call (static overrides only)."""
    resolved = git or git_executable()
    return {**_base_environment(resolved), **_config_environment(NEUTRALIZED_CONFIG)}


def _base_environment(git: str) -> dict[str, str]:
    return {
        "PATH": os.pathsep.join(dict.fromkeys((str(Path(git).parent), "/usr/bin", "/bin"))),
        "HOME": os.devnull,
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_PAGER": "cat",
        "PAGER": "cat",
    }


def _config_environment(overrides: Sequence[tuple[str, str]]) -> dict[str, str]:
    # GIT_CONFIG_COUNT keeps keys and values separate, so driver names containing
    # "=" or spaces cannot be misparsed the way `-c key=value` could be.
    env = {"GIT_CONFIG_COUNT": str(len(overrides))}
    for index, (key, value) in enumerate(overrides):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    return env


def _driver_overrides(
    git: str,
    cwd: str,
    base: dict[str, str],
    timeout: float,
) -> list[tuple[str, str]]:
    """Blank the command of every filter/diff driver the repository defines.

    Reading config never executes anything; it does follow config includes.
    """
    completed = subprocess.run(
        [git, "config", "--null", "--get-regexp", r"^(filter|diff)\."],
        cwd=cwd,
        env={**base, **_config_environment(NEUTRALIZED_CONFIG)},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    drivers: set[tuple[str, str]] = set()
    for entry in completed.stdout.split(b"\0"):
        key = entry.split(b"\n", 1)[0].decode("utf-8", errors="surrogateescape")
        match = _DRIVER_KEY.match(key)
        if match:
            drivers.add((match.group(1), match.group(2)))
    return [
        (f"{section}.{name}.{command}", "")
        for section, name in sorted(drivers)
        for command in DRIVER_COMMANDS[section]
    ]


def _empty_tree(git: str, cwd: str, base: dict[str, str], timeout: float) -> str | None:
    completed = subprocess.run(
        [git, "hash-object", "-t", "tree", "--no-filters", os.devnull],
        cwd=cwd,
        env={**base, **_config_environment(NEUTRALIZED_CONFIG)},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    tree = completed.stdout.strip()
    return tree if completed.returncode == 0 and tree else None
