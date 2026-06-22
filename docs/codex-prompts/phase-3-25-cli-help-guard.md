# Codex Prompt — Phase 3.25 CLI Help and Introspection Guard

## Role

You are working inside the canonical ARI repo.

Do not redesign ARI. Do not build ACE UI. Do not add external API integrations. Do not implement autonomous execution.

Your job is to add a small CLI guard so help/introspection commands never route into Codex, OpenAI, or any worker loop.

## Context

A terminal demo exposed a CLI design flaw.

Commands like:

- `python -m ari_core.ari --help`
- `python -m ari_core.ari execution --help`
- `python -m ari_core.ari execution context --help`

were incorrectly treated as natural-language goals and routed into the Codex worker loop.

This wasted worker calls and created confusing output.

## Objective

Add a local command-mode guard for help/introspection inputs.

Help commands should return local help text or structured local introspection output.

They must not:

- invoke Codex
- invoke OpenAI
- invoke any external API
- create worker runs
- create runtime loops
- mutate repo state

## Required Inputs to Handle

At minimum:

- `--help`
- `-h`
- `help`
- `execution --help`
- `execution help`
- `execution context --help`
- `execution context help`
- `execution plans --help`
- `execution plans help`

## Requirements

1. Add the smallest reasonable guard in the CLI entry path.
2. Preserve existing natural-language goal routing.
3. Preserve existing `plan_only` behavior for actual planning requests.
4. Preserve existing `codex_loop` behavior for implementation-like requests.
5. Add tests proving help commands do not create worker runs.
6. Add tests proving help commands do not route to `codex_loop`.
7. Add tests proving normal implementation-like requests still route as before.
8. Keep output simple and stable.
9. Update docs if there is an existing CLI documentation location.

## Suggested Behavior

For top-level help, return a local structured response with:

- available command categories
- examples
- note that natural-language goals are supported

For execution help, include:

- execution context
- execution plans
- plan preview
- local inspection commands
- warning that help does not invoke workers

Do not overbuild argparse/Typer unless already used. Prefer a small guard compatible with current CLI architecture.

## Verification

Run:

    .venv312/bin/python -m pytest tests/unit -q
    .venv312/bin/python -m ruff check .
    git status

## Suggested Commit Messages

1. Add CLI help routing guard
2. Test local help commands avoid worker routing
3. Document CLI help guard

## Non-Goals

- Do not connect the Responses API in this task.
- Do not modify ACE.
- Do not add GitHub integration.
- Do not implement command execution.
- Do not refactor the whole CLI.
