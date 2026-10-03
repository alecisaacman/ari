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
