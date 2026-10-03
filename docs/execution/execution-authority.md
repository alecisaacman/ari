# Execution Authority

This document describes what ARI's own execution tools are *allowed to ask for*.
It is an authority boundary, not OS containment. Nothing here confines code that
ARI runs: a test suite, a `conftest.py`, or any other program ARI starts can do
whatever the operating-system user can do. Real process isolation is a later
milestone.

## Execution roots

`fs_authority.configured_execution_root()` is the only source of filesystem
authority:

- `ARI_EXECUTION_ROOT` if set
- never `/`
- never equal to, inside, or containing ARI state storage (`ARI_HOME` and the
  database directory)
- never equal to, inside, or containing ARI's **live runtime**: the source
  checkout ARI runs from (`PROJECT_ROOT`) and its Python environment (`sys.prefix`,
  `sys.exec_prefix`, `sys.base_prefix`)

If `ARI_EXECUTION_ROOT` is unset, the fallback is the project root, which *is* the
live checkout. **Execution therefore fails closed with a configuration error.**
The operator environment variable `ARI_ALLOW_SELF_MODIFICATION=1` (exactly `1`)
lifts the live-runtime rule for deliberate ARI self-development. It is read only
from ARI's own process environment; no API or CLI parameter can set it. Even with
the override, the Python environment, `.git`, migrations, schema, and state remain
protected paths.

Every requested root must resolve, after symlinks, to the configured root or a
descendant of it, and must satisfy the same overlap rules. Relative requests
resolve against the configured root. This applies to:

- `ExecutionRoot(...)` directly, and so to the controller, coding loop, planners,
  and `execute_action`
- the recovered-action gateway (resolved lazily, so read-only task inspection works
  without a configured root)
- `POST /execution/coding-loop` (`executionRoot`) and `GET /execution/context`
  (`executionRoot`)
- the CLI `--execution-root` options on `api execution goal|plan|coding-loop|context`
- the operator engine (`modules/execution/engine.py`) and its API/CLI endpoints,
  which always use the configured root

A rejected root is a `ValueError`, which surfaces as HTTP 400 on the API.

## Protected internal paths

Mutating tools (`write_file`, `patch_file`, and the operator engine's write and
patch operations) refuse targets beneath:

- `config/migrations/` and `config/schema.sql`, relative to any execution root,
  and ARI's own migration directory and schema file
- any `.git` directory
- ARI state storage and the legacy state directory
- ARI's Python environment (`sys.prefix`, `sys.exec_prefix`, `sys.base_prefix`)

Comparisons are case-insensitive and also check the identity of existing
ancestors, so case variants and directory aliases of these paths are caught.
These rules apply only to ARI execution tools. Normal developer editing is
unaffected.

## File writes

`fs_authority.replace_text_atomically` is shared by `ExecutionRoot` and the
operator engine:

- a requested path whose final component is a symlink is refused, so a write never
  goes *through* a link, even to an in-root target
- an existing target must be a regular file with exactly one hard link
- content goes to a same-directory temporary file created with `O_EXCL`, is
  fsynced, then `os.replace`d into place. Readers see the old or the new file, and
  a failure leaves the target untouched.
- an existing file keeps its permission bits. A new file gets `0o666` minus the
  process umask.
- parent confinement and the target checks are re-run immediately before the
  rename

**Residual risk:** without `openat`-style directory handles, a concurrent local
process that can swap a parent directory for a symlink between the final
revalidation and `os.replace` could still redirect the rename.

## File reads

Read confinement is a **validated path within the execution root**, not proof of
which inode is read:

- `read_file` (and the read half of `patch_file`) opens the resolved path with
  `O_NOFOLLOW` on the final component, requires a regular file, and refuses files
  with more than one hard link, because a hard link can alias a file outside the
  root.
- `cat` refuses a requested path whose final component is a symlink and refuses
  multiply-linked regular files. `ls` arguments are validated paths; `ls` reports
  names and metadata, not file contents.
- **Residual TOCTOU:** `cat` and `ls` re-open their arguments by path after ARI
  validates them, and intermediate directories are resolved by path for all
  reads. A concurrent local process that swaps a component for a symlink or hard
  link in that window can redirect the read. Code-execution capabilities can
  create such races; the read-only capabilities do not.

## Command capabilities

`run_command` actions (`ExecutionRoot.run_command`) and operator command strings
(`engine.execute_command`, `POST /execution/command`, operator verify commands)
resolve to exactly one capability in `command_capabilities.py`. Anything else is
refused. A request names a logical command. The capability validates its argv shape
and builds the argv itself, starting from an executable at a **fixed location
selected by ARI**. Binary identity is not cryptographically verified, and the
requested executable path is never run.

| Capability | Class | Executable (fixed location, not verified) | Permitted shape | Paths |
| --- | --- | --- | --- | --- |
| `ls` | read-only inspection | `ls` in `/bin` or `/usr/bin` | `-1 -a -A -l -la -al -lA -Al -F`, then paths (ARI inserts `--`) | validated paths within the root |
| `cat` | read-only inspection | `cat` in `/bin` or `/usr/bin` | paths only (ARI inserts `--`) | validated paths; no final symlink, no multiply-linked file |
| `pytest` | code execution | `sys.executable -P -m pytest` | `-q -v -x -s --no-header -k EXPR -m EXPR --tb=STYLE --maxfail=N`, test paths / node ids | validated paths within the root |
| `node` | code execution | first `node` in `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin`, `/bin` (these may be user-writable) | `node --check <file>` or `node --test <file>...` | validated paths within the root |

- `npm` and `npx` are refused. npm scripts are arbitrary package-defined code, and
  no narrow, honest capability is defined.
- Python identity: `pytest`, `python -m pytest`, or any path whose final component
  is exactly `python`, `python3`, `python3.N` (or the running interpreter's name)
  requests pytest under ARI's own interpreter. `python-evil` and similar names are
  rejected. A requested interpreter path is never executed. `sys.executable` is
  whatever interpreter runs ARI; with the live-runtime rule, ARI's tools cannot
  modify it unless the operator override is set, and even then its environment is
  a protected path.

### What the pytest invocation pins

Requested pytest options that change where pytest reads config, writes output, or
what it loads are refused, including `--junitxml`, `--basetemp`,
`-o`/`--override-ini`, `--rootdir`, `-c`/`--config-file`, `-p`, `--debug`,
`--log-file`, `--confcutdir`, `-W`, `--import-mode`, `--pdb`, and `@argfile`, in both
`=` and separate-value forms. ARI itself generates:

- `-P`: the cwd (the execution root) is not put on `sys.path`, so a root-local
  `pytest.py` or `pytest/` package cannot replace the installed pytest
- `-c <root config or /dev/null> --rootdir <root> --confcutdir <root>`: a
  `pytest.ini`, `pyproject.toml`, or `conftest.py` *above* the root is not
  discovered
- `-o addopts= -o pythonpath= -o testpaths= -o log_file= -p no:cacheprovider`: the
  root's own config cannot add refused options, extend `sys.path` beyond the root,
  choose collection roots outside it, or write logs or cache files elsewhere
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and `PYTHONNOUSERSITE=1`: plugins installed in
  the interpreter environment are not auto-loaded

This pins how ARI *starts* pytest. It does not limit the code pytest then runs:
`conftest.py`, test modules, and plugins they request (`pytest_plugins`) are
arbitrary local code.

### Classification and restrictions

`run_command` is registered with `mutates_files=True`. Only `ls` and `cat` are
read-only inspection. `pytest` and `node` are code execution: they run local code
that can read, write, spawn, and use the network as the OS user. The
recovered-action gateway lets a task restricted to `read only`, `read-only`,
`no mutations`, or `no file writes` run only read-only inspection capabilities.

### Environment for spawned capabilities

The child environment is built from scratch, not inherited:

- `PATH`: the selected executable's directory plus `/bin:/usr/bin`
- `LANG`/`LC_ALL`/`LC_CTYPE` copied when set (`LANG` defaults to `C.UTF-8`)
- for code execution, `HOME` and `TMPDIR`/`TMP`/`TEMP` under `<root>/.ari-exec/`.
  These are created relative to directory descriptors with `O_NOFOLLOW`, so a
  pre-existing symlink at `.ari-exec`, `.ari-exec/home`, `.ari-exec/tmp`, or
  `.ari-exec/.gitignore` is refused rather than followed.
- pytest additionally gets the variables listed above
- `PYTEST_ADDOPTS`, `PYTEST_PLUGINS`, `PYTHONPATH`, `PYTHONSTARTUP`, `PYTHONHOME`,
  `NODE_OPTIONS`, and `NODE_PATH` are never present
- macOS itself adds `__CF_USER_TEXT_ENCODING`

This is not a secret-scrubbing design. It keeps ARI's own environment out of the
child, but code execution can still read anything the OS user can, including files.

### Process groups

Each command runs as the leader of a new session/process group with stdin closed.
**ARI signals the group only while it has not yet reaped the leader.** An unreaped
leader, running or a zombie, keeps its PID and therefore the group ID reserved,
so a signal cannot reach an unrelated group that reused the number.

- Timeout (leader still running at the deadline): `SIGTERM` to the group, a grace
  period, `SIGKILL` to the group, then reap and raise `TimeoutExpired`.
- Normal return: ARI waits for the leader to exit *without reaping it* (kqueue
  `NOTE_EXIT` on macOS, `waitid(WNOWAIT)` where available), sends `SIGKILL` to any
  remaining group members, then reaps. If a group member holds the output pipes
  after the leader exits, the result is still returned, not reported as a timeout.
- On a platform with neither non-reaping primitive, ARI reaps without post-return
  cleanup rather than risk signalling a reused group ID.

Limits: a descendant that calls `setsid` or daemonizes leaves the group. The
ownership rule assumes nothing else in the ARI process reaps arbitrary children
(`waitpid(-1)`). This is cleanup, not containment. **`run_command` remains
`unbounded` for redispatch, and no cleanup step creates a landing token.**

## Internal Git inspection

ARI's own read-only Git inspection is a separate path from the capabilities. It
covers `git status --short`, `git branch --show-current` (controller repo context),
`git status --short` and `git diff --shortstat` (runtime repo inspector), and
`git log`/`git diff --name-only` over a commit range (self-documentation seeds).
These all go through `core/git_inspection.run_git_inspection`:

- the environment is constructed, not inherited: no ambient `GIT_*` variables and
  none of ARI's own variables
- global and system Git config and attributes are ignored
- `GIT_OPTIONAL_LOCKS=0`
- `core.fsmonitor` is disabled, `core.hooksPath` points at `/dev/null`,
  `diff.external` is empty, and signature display is off
- attributes are read from the empty tree, and every filter and diff driver defined
  in the repository's config has its commands blanked, so `.gitattributes` and
  `.git/info/attributes` cannot select a program
- `--no-ext-diff --no-textconv` for diff/log, and submodules are ignored
- `git` comes from a fixed location (`/opt/homebrew/bin`, `/usr/local/bin`,
  `/usr/bin`, `/bin`; not verified), runs without a shell, and has a timeout.
  Git 2.40 or newer is required for `--attr-source`; older Git makes inspection
  report "unavailable".
- callers pass `--end-of-options` before commit ranges, so a ref cannot become an
  option such as `--output=<file>`

This hardens exactly these commands against the repository-controlled execution
mechanisms listed. It does not make arbitrary Git operations on an untrusted
repository safe, and `core.worktree` can still point inspection (read-only) at a
directory outside the root.

## What is still outside this boundary

These paths start processes or write files without these rules:

- legacy `ari_core/executor.py` + `ari_core/authority.py`: exact-string
  `pytest -q` in the repo root, via the ambient `PATH` and environment, with no
  timeout (arbitrary local code)
- `runtime/verification_profiles.py`: profile-defined commands with the inherited
  environment (arbitrary local code)
- `runtime/worker_backend.py`, `runtime/self_improvement_runner.py`: provider
  workers such as `codex exec` (operator-configured arbitrary code)
- `runtime/playground.py`: `git init/config/add/commit` with the inherited
  environment, and a recursive workspace reset on an operator-supplied path. By code
  reading, that reset's `is_dir()` check follows symlinked directories, so it can
  delete a link target's contents (operator-controlled).
- documentation suits (`ffmpeg`, `screencapture`) and the career-command adapter
  (operator-controlled)
- task restrictions are enforced only by the recovered-action gateway, not by
  `ExecutionController.run()`, the coding loop, or operator actions
- a `no network` restriction is not enforced against code-execution capabilities
