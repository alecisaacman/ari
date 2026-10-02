# ARI

ARI is local-first personal intelligence infrastructure: one canonical system
that owns memory, state, authority, decisions, and continuity while replaceable
model providers and interface surfaces do bounded work around it.

> **ARI is the brain. ACE is how it appears. Models are workers, not owners.**

The project is being built toward a personal intelligence operating system that
can survive provider changes, context exhaustion, rate limits, process crashes,
and interrupted sessions without losing task truth or widening authority.

## Current milestone

As of October 1, 2026, the current development branch has a durable execution
ledger, leased worker-session recovery, and an ARI-owned authority gateway that
can authorize and execute exactly one recovered pending action.

The verified Python suite is currently **495 passing tests**.

### What works now

- Canonical local state in SQLite
- Goals, tasks, open loops, memory, signals, alerts, and orchestration history
- Bounded file and allowlisted command execution inside an execution root
- Continuous execution checkpoints and ordered audit events
- Stable task identity across worker loss and replacement attempts
- Worker leases, heartbeats, stale-session detection, and continuation packets
- Replacement-worker acknowledgement without authority expansion
- Action-digest-bound approvals for recovered work
- Durable idempotency and uncertain-effect handling
- Exactly one recovered side effect per explicit ARI resume decision
- Read-only API inspection for execution, decisions, evidence, and pending work
- ACE Hub and Telegram surfaces that remain clients of canonical ARI state

### What is not claimed yet

- No Anthropic or Claude integration
- No cross-provider routing or failover
- No automatic local-model routing
- No fully converged execution gateway across every legacy path
- No unrestricted autonomous coding agent
- No claim that ACE, Codex, or any provider can independently authorize actions

## How the system fits together

```text
Human intent and external events
            |
            v
       ARI canonical core
  state | memory | policy | goals
  decisions | approvals | audit
            |
            v
   Durable Execution Fabric
 task -> attempt -> checkpoint -> decision
            |
            v
 ARI authority and tool gateway
            |
            v
 Replaceable worker/provider adapters
            |
            v
     verified result + evidence

ACE Hub / Telegram / future mobile and voice surfaces
read from and submit intent to the same ARI core
```

The source-bearing Git checkout is the canonical implementation. ARI-owned
SQLite is the canonical local execution store. Provider processes and surfaces
are replaceable workers and clients, never alternate sources of task truth. See
[ADR 0001](docs/adr/0001-canonical-source-and-execution-store.md).

## The build story

| Period | Progress | Friction and lesson |
|---|---|---|
| April 2026 | Built the state, event, persistence, orchestration, CLI, API, and first Hub spine. | Early prototypes were fragmented. The project had to converge on one repository and one canonical state model. |
| May 2026 | Clarified the product narrative, public roadmap, and security posture. | The vision was ahead of the runtime. Documentation had to distinguish intended architecture from working behavior. |
| June 2026 | Added the kill switch, approval/governance foundation, operator surfaces, runtime decisions, and memory loops. | Execution existed through several paths, but continuity and authority were not yet unified. |
| September 2026 | Added the provider-neutral durable execution ledger. | Tasks could be described durably, but a dead worker still needed an explicit recovery lifecycle. |
| September 2026 | Added leases, heartbeats, stale-attempt reconciliation, continuation packets, and acknowledgement. | Recovery could reach `execution_ready`, but deliberately stopped before another side effect. |
| October 2026 | Added the recovered-action authority gateway, action-bound approval, idempotency, verification, and one-action execution cadence. | Legacy execution paths still need convergence before provider routing is safe. |

The detailed account, including decisions, dead ends, and evidence, lives in
[The ARI Build Journey](docs/BUILD-JOURNEY.md).

## Repository map

| Path | Responsibility |
|---|---|
| `services/ari-core` | Canonical intelligence, state, policy, execution, and verification |
| `services/ari-api` | Service contract over canonical ARI capabilities |
| `services/ari-hub` | ACE web surface for inspection and controlled interaction |
| `packages/ari-memory` | Durable memory repositories and persistence contracts |
| `packages/ari-state` | Shared state and decision models |
| `packages/ari-events` | Event normalization and classification |
| `packages/ari-telegram-gateway` | Mobile natural-language intake into ARI |
| `config/migrations` | Immutable SQLite execution-fabric migrations |
| `docs/execution` | Execution ledger, recovery, safety, and gateway contracts |
| `tests/unit` | Deterministic behavioral and architecture tests |

## Near-term direction

1. Converge remaining execution paths on the same ARI authority boundary.
2. Persist and validate execution-root and sandbox policy as canonical task authority.
3. Introduce provider adapters behind a provider-neutral worker contract.
4. Add capability and availability routing without hard-coding current model names.
5. Add same-task provider failover using the existing checkpoint and acknowledgement flow.
6. Add replaceable local inference adapters after continuity and authority are proven.

See the [roadmap](docs/roadmap.md), [current architecture](docs/status/current-architecture.md),
[open blockers](docs/status/open-blockers.md), and [next implementation slice](docs/status/next-step.md).

## Local setup

Python 3.12 or newer is required.

```bash
python3.12 -m venv .venv312
.venv312/bin/python -m pip install -e .
.venv312/bin/python -m pytest -q -p no:cacheprovider
.venv312/bin/python -m ruff check packages services tests --no-cache
```

Useful starting points:

- `ari --help`
- `GET /execution/tasks/{task_id}`
- [Execution session recovery](docs/execution/session-recovery.md)
- [Recovered action gateway](docs/execution/recovered-action-gateway.md)
- [Telegram gateway](docs/telegram-gateway.md)

## Operating principles

- One brain and one canonical state model
- Human authority preserved across every worker handoff
- Continuous checkpointing instead of last-minute handoff prose
- Local-first persistence and inspectable provenance
- Bounded tools, explicit approvals, and verified outcomes
- Honest status: implemented behavior is separated from planned behavior
- Provider independence without pretending providers are interchangeable today

## Security

ARI is intentionally conservative about side effects. Execution uses bounded
roots and command allowlists, approvals bind to exact actions and resources, and
uncertain effects are not blindly retried. See [SECURITY.md](SECURITY.md).
