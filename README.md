# ARI

ARI is a local-first personal intelligence system — it runs on your own machine, holds its
own memory, and acts under explicit policy rather than unconstrained autonomy.

**ARI is the brain. ACE is how it shows up across surfaces.**

The source-bearing Git checkout is the canonical implementation. ARI-owned SQLite is the
canonical local execution store; provider processes and interface surfaces are replaceable
workers and clients, not sources of task truth. See
[ADR 0001](docs/adr/0001-canonical-source-and-execution-store.md).

## What's here

| Path | Role |
|---|---|
| `services/ari-core` | Canonical runtime — memory, decisions, execution |
| `services/ari-api` | API contract over `ari-core` |
| `services/ari-hub` | Surface for inspecting and driving ARI |
| `packages/ari-telegram-gateway` | Natural-language intake over Telegram |

## Design principles

- **One brain.** Every surface — terminal, hub, Telegram — talks to the same canonical
  runtime. Nothing lives only in a surface.
- **Bounded execution.** ARI acts under policy: typed decisions (act, escalate, defer,
  ignore), verified results, and a persisted trail for every autonomous step.
- **Durable continuity.** Execution tasks, attempts, ordered events, append-only
  checkpoints, and normalized results live independently of the executing worker.
- **Local-first, not local-only.** Your machine is the primary execution host today.
  Other surfaces — mobile, cloud workers — extend the brain; they never replace it.

## Getting started

```bash
pip install -e .
ari --help
```

To add the Telegram intake surface, see
[docs/telegram-gateway.md](docs/telegram-gateway.md).

## Status

ARI is under active, daily development. The core runtime, API, and execution loop are
real and tested; autonomous coding is still bounded and supervised. See
[docs/](docs/) for architecture detail.

## Security

See [SECURITY.md](SECURITY.md).
