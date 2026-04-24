# ARI Safe Command Policy

## Status

ARI is entering safe verification authority.

The command policy validates proposed verification commands before they can be
used in planning, previews, or future verification loops. It does not execute
commands.

## Authority Boundary

ARI remains the authority layer. The policy lives in canonical ARI execution code
and is deterministic, local, typed, inspectable, and fail-closed.

ACE and other interfaces may display command policy results, but they must not
own or duplicate the policy.

## What It Does

`validate_command(command, repo_root)` returns a typed result with:

- whether the command is allowed
- the original command
- the reason
- a rejection code when blocked
- the normalized command when allowed
- the safe category when allowed

The policy only validates. It does not run commands, mutate files, install
packages, contact networks, or approve execution.

## Allowed Categories

The first version is intentionally conservative:

- full unit tests: `.venv312/bin/python -m pytest tests/unit -q`
- focused unit tests under `tests/unit/*.py`
- ruff checks over safe repo paths
- git inspection: `git status --short`, `git diff --stat`, and `git diff -- <path>`
- read-only directory listing: `ls <safe_repo_path>`

## Rejected Categories

Anything outside the explicit allowlist is rejected, including:

- destructive commands such as `rm`, `mv`, `chmod`, `chown`
- privilege escalation such as `sudo` or `su`
- network commands such as `curl`, `wget`, `ssh`, `scp`, `rsync`
- package installs such as `pip install`, `npm install`, or `brew install`
- mutating git commands such as `push`, `commit`, `reset`, `checkout`, or `clean`
- Docker, Node package managers, arbitrary shell scripts, and arbitrary Python scripts
- commands using pipes, redirects, shell chaining, backticks, command substitution, or env expansion
- paths with parent traversal, unsafe wildcards, or locations outside the repo root

## Current Integration

Strict OpenAI planner output validates verification commands through this policy
before output reaches `ModelPlanner`.

Generic `ModelPlanner` verification parsing also validates any provided
verification command. Unsafe commands fail closed during planning/preview.

## Non-Goals

This policy does not enable command execution. Execution remains disabled until a
future approval boundary exists.
