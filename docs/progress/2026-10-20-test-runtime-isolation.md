# Test and Runtime Isolation Handoff

## Scope

Branch `codex/test-runtime-isolation` starts exactly at
`51c149dd4a22579740b36c438af495ed0c5938fe`. This slice isolates Python and hub
tests, resolves the canonical Python runtime without assuming `.venv/bin/python`,
and makes source-checkout and LaunchAgent diagnostics explicit. It does not change
the execution semantics in `gateway.py`, `dispatch.py`, `session.py`, or
`reconciliation.py`.

## Changes

- Python tests set isolated ARI home, execution-root, and surface-status paths
  before test collection. A session guard fingerprints the live networking database
  and every file in the canonical surface-status tree and fails if any hash, mtime,
  size, existence state, or directory membership changes.
- Hub tests use `ARI_CANONICAL_PYTHON`, then repository `.venv312`, then `.venv`,
  and set isolated state/status paths for subprocess and API-backed execution.
- Repository tools resolve the source-bearing checkout from their own location and
  share deterministic Python discovery through `scripts/lib/ari_runtime.sh`.
- `tools/ari-test` runs the complete Python suite, all hub tests, and the hub build
  inside a temporary runtime root.
- LaunchAgent status reports missing targets and working directories without
  modifying installed agents. The Telegram installer has a read-only `--check`,
  refuses implicit replacement, and diagnoses missing source/runtime targets.

## Verification

- Python: `865 passed, 1 warning`
- Ruff: passed
- Hub: `28 passed, 0 failed`
- Hub production build: passed
- Shell syntax and `git diff --check`: passed
- Installed LaunchAgent inspection: all four existing agents clearly report their
  missing executable targets; no plist was changed
- Installer preflight: passed in `--check` mode; no file was written

Protected live files remained at their preflight values:

- `~/ARI/modules/networking-crm/state/networking.db`: SHA-256
  `225c461f041e8be224e2b505d5d00817a1f7a1d4426ae62cb2c5a0a79e31fa95`,
  mtime `1792548335`, size `2609152`
- canonical `data/surface/status/current.json`: SHA-256
  `5126d7c1a23796edb0ae4b47a8d12c16dccec2d654f128b7122725c3878250fd`,
  mtime `1792548342`, size `457`
- No surface-status history file is newer than that protected `current.json`.

## Integration

Keep this commit local. Merge this Codex branch first, then rebase Claude commit
`314519c` (`claude/execution-convergence`) onto the result and run the complete
verification matrix. Do not push, merge to the shared integration branch, or alter
PR #7 until both tracks pass together. Claude also reported that its worktree needs
`cryptography` and `requests`; reconcile those declared dependencies during the
combined verification rather than relying on worktree-local installs.
