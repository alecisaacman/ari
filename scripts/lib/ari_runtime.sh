#!/usr/bin/env bash

# Shared path/runtime discovery for repository-owned operator scripts.
# This file is sourced; it intentionally does not enable shell options globally.

ari_repo_root_from_path() {
  local anchor_path="$1"
  local anchor_dir
  anchor_dir="$(cd "$(dirname "$anchor_path")" && pwd -P)"
  git -C "$anchor_dir" rev-parse --show-toplevel 2>/dev/null
}

ari_resolve_python() {
  local repo_root="$1"
  local configured="${ARI_CANONICAL_PYTHON:-}"
  local candidate

  if [[ -n "$configured" ]]; then
    if [[ -x "$configured" ]]; then
      (cd "$(dirname "$configured")" && printf '%s/%s\n' "$PWD" "$(basename "$configured")")
      return 0
    fi
    if command -v "$configured" >/dev/null 2>&1; then
      command -v "$configured"
      return 0
    fi
    echo "Configured ARI_CANONICAL_PYTHON is not executable: $configured" >&2
    return 1
  fi

  for candidate in \
    "$repo_root/.venv312/bin/python" \
    "$repo_root/.venv/bin/python"
  do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  if command -v python3.12 >/dev/null 2>&1; then
    command -v python3.12
    return 0
  fi

  echo "No ARI Python 3.12 runtime found for: $repo_root" >&2
  echo "Set ARI_CANONICAL_PYTHON or create $repo_root/.venv312." >&2
  return 1
}
