# Execution Authority

This document describes what ARI's own execution tools are *allowed to ask for*.
It is an authority boundary, not OS containment. Nothing here confines code that
ARI runs: a test suite, a `conftest.py`, or any other program ARI starts can do
whatever the operating-system user can do. Real process isolation is a later
milestone.

## Execution roots

`fs_authority.configured_execution_root()` is the only source of filesystem
authority:

- `ARI_EXECUTION_ROOT` if set, otherwise the project root
- never `/`
- never equal to, inside, or containing ARI state storage (`ARI_HOME` and the
  database directory)

Every requested root must resolve, after symlinks, to the configured root or a
descendant of it, and must not overlap ARI state. Relative requests resolve
against the configured root. This applies to:

- `ExecutionRoot(...)` directly, and so to the controller, coding loop, recovered
  action gateway, and `execute_action`
- `POST /execution/coding-loop` (`executionRoot`)
- `GET /execution/context` (`executionRoot`)
- the CLI `--execution-root` options on `api execution goal|plan|coding-loop`
- the operator engine (`modules/execution/engine.py`), which always uses the
  configured root

A rejected root is a `ValueError`, which surfaces as HTTP 400 on the API.
`/`, sibling directories, `..` escapes, and symlinked escapes are all rejected.

## Protected internal paths

Mutating tools (`write_file`, `patch_file`, and the operator engine's write and
patch operations) refuse targets beneath:

- `config/migrations/` and `config/schema.sql`, relative to any execution root,
  and ARI's own migration directory and schema file
- any `.git` directory
- ARI state storage and the legacy state directory

Comparisons are case-insensitive and also check inode identity, so case or alias
variants do not bypass them. Reads are not restricted. These rules apply only to
ARI execution tools. Normal developer editing is unaffected.

## Safe file replacement

`fs_authority.replace_text_atomically` is shared by `ExecutionRoot` and the
operator engine:

- a requested path whose final component is a symlink is refused, so a write
  never goes *through* a link, even to an in-root target
- an existing target must be a regular file with exactly one hard link, so an
  inode shared with a file outside the root cannot be overwritten
- content goes to a same-directory temporary file created with `O_EXCL`, is
  fsynced, then `os.replace`d into place. Readers see the old or the new file,
  never a partial one, and a failure leaves the target untouched.
- an existing file keeps its permission bits. A new file gets `0o666` minus the
  process umask, like an ordinary write.
- parent confinement and the target checks are re-run immediately before the
  rename
- reads for patching (and `read_file`) open with `O_NOFOLLOW`

**Residual risk:** without `openat`-style directory handles, a concurrent local
process that can swap a parent directory for a symlink between the final
revalidation and `os.replace` could still redirect the rename. Closing that window
needs descriptor-relative operations or OS isolation.

## Command capabilities

`run_command` actions (`ExecutionRoot.run_command`) and operator command strings
(`engine.execute_command`, `POST /execution/command`, operator verify commands)
resolve to exactly one capability in `command_capabilities.py`. Anything else is
refused. A request names a logical command. The capability validates its argv
shape and builds the argv from a trusted executable; the requested executable
path is never run.

| Capability | Class | Trusted executable | Permitted shape | Paths |
| --- | --- | --- | --- | --- |
| `ls` | read-only inspection | `/bin` or `/usr/bin` `ls` | `-1 -a -A -l -la -al -lA -Al -F`, then paths (ARI inserts `--`) | confined to root |
| `cat` | read-only inspection | `/bin` or `/usr/bin` `cat` | paths only (ARI inserts `--`) | confined to root |
| `pytest` | code execution | `sys.executable -m pytest` | `-q -v -x -s --no-header -k EXPR -m EXPR --tb=STYLE --maxfail=N`, test paths / node ids | confined to root |
| `node` | code execution | `node` from system install dirs, not the caller's `PATH` | `node --check <file>` or `node --test <file>...` | confined to root |

- `npm` and `npx` are refused. npm scripts are arbitrary package-defined code, and
  no narrow, honest capability is defined.
- Python identity: `pytest`, `python -m pytest`, or any path whose final component
  is exactly `python`, `python3`, `python3.N` (or the running interpreter's name)
  requests pytest under ARI's own interpreter. `python-evil` and similar names are
  rejected. A requested interpreter path is never executed.
- Pytest options that change where pytest reads config, writes output, or what it
  loads are refused, including `--junitxml`, `--basetemp`, `-o`/`--override-ini`,
  `--rootdir`, `-c`/`--config-file`, `-p`, `--debug`, `--log-file`, `--confcutdir`,
  `-W`, `--import-mode`, `--pdb`, and `@argfile`, in both `=` and separate-value
  forms. ARI itself generates `-c <root config or /dev/null> --rootdir <root>
  --confcutdir <root>`, so a `pytest.ini` or `conftest.py` *above* the root cannot
  inject options or code. (`-c /dev/null` alone would move `confcutdir` out of the
  root and load parent conftest files.)

### Classification and restrictions

`run_command` is registered with `mutates_files=True`. Only `ls` and `cat` are
read-only inspection. `pytest` and `node` are code execution: a test,
`conftest.py`, or script is arbitrary local code that can read, write, spawn, and
use the network as the OS user. ARI constrains what it *requests*, not what that
code does. The recovered-action gateway lets a task restricted to `read only`,
`read-only`, `no mutations`, or `no file writes` run only read-only inspection
capabilities.

### Environment

The child environment is built from scratch, not inherited:

- `PATH`: the trusted executable's directory plus `/bin:/usr/bin`
- `LANG`/`LC_ALL`/`LC_CTYPE` copied when set (`LANG` defaults to `C.UTF-8`)
- for code execution, `HOME` and `TMPDIR`/`TMP`/`TEMP` under
  `<root>/.ari-exec/` (git-ignored via its own `.gitignore`)
- `PYTEST_ADDOPTS`, `PYTEST_PLUGINS`, `PYTHONPATH`, `PYTHONSTARTUP`, `PYTHONHOME`,
  `NODE_OPTIONS`, and `NODE_PATH` are never present

This is not a secret-scrubbing design. It narrows what reaches the child, but code
execution can still read anything the OS user can.

### Process groups

Each command runs as the leader of a new session/process group with stdin closed.
On timeout ARI sends `SIGTERM` to the group, then `SIGKILL`, and raises
`TimeoutExpired`. After a normal return it sends `SIGKILL` to any remaining group
members. If a group member keeps the output pipes open after the direct child
exits, the group is killed and the result is returned rather than reported as a
timeout. This is cleanup, not containment: a descendant that calls `setsid` or
daemonizes leaves the group. **`run_command` remains `unbounded` for redispatch,
and no cleanup step creates a landing token.**

## What is still outside this boundary

These paths start processes or touch files without these capabilities:

- `ExecutionController` repo-context helpers run fixed `git status --short` /
  `git branch --show-current` inside the confined root (internal, read-only)
- legacy `ari_core/executor.py` + `ari_core/authority.py` command allowlist
- `runtime/verification_profiles.py`, `runtime/worker_backend.py`,
  `runtime/repo_inspector.py`, `runtime/playground.py`
- documentation suits (`suits/documentation/*`), `self_documentation/content_seed.py`
- `packages/ari-career-command` adapter subprocesses
- task restrictions are enforced only by the recovered-action gateway, not by
  `ExecutionController.run()`, the coding loop, or operator actions
- a `no network` restriction is not enforced against code-execution capabilities
