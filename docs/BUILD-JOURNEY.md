# The ARI Build Journey

This document records how ARI has evolved, what became real, what broke or
proved incomplete, and why the current architecture prioritizes durable
continuity and authority before broad autonomy.

It is a build record, not a claim that every item in the long-term vision is
already implemented.

## The objective

ARI is intended to become model-provider-independent personal intelligence
infrastructure. ARI owns identity, memory, state, goals, projects, tasks,
permissions, approvals, orchestration, audit, and decisions.

ACE is the manifestation layer: Hub, Telegram, terminal, mobile, notifications,
and future voice or companion surfaces. ACE can present state and submit intent,
but it must never become a competing brain.

Models are replaceable workers. A task should survive a provider change, context
limit, rate limit, timeout, worker crash, or interrupted session without losing
its objective, completed work, restrictions, approvals, or evidence.

## Timeline

### April 2026: foundation and convergence

ARI began with a practical local spine:

- typed state and event models
- SQLite persistence
- daily and weekly routines
- signals and alerts
- orchestration history
- CLI, API, and read-only Hub views

The first major difficulty was fragmentation. Prototype ARI and ACE work existed
in different shapes, and passing data between surfaces risked creating multiple
sources of truth. The resolution was structural convergence: `ari-core` became
canonical, `ari-api` became the service boundary, and the Hub became a client.

Lesson: interface progress is not architectural progress if state ownership is
ambiguous.

### May 2026: product clarity exceeded runtime maturity

The product narrative, roadmap, and security posture became clearer. Career
Command emerged as the first serious proof workflow, and Telegram became the
most practical early mobile surface.

The difficult truth was that the vision described a durable operating system
while execution remained narrow. Documentation was revised to separate current
behavior from intended behavior.

Lesson: a credible system needs explicit evidence for what works and equally
explicit boundaries around what does not.

### June 2026: governance before autonomy

ARI gained:

- a global execution kill switch
- approval and governance foundations
- operator execution surfaces
- bounded file and command tooling
- runtime decision and memory loops
- clearer public architecture documentation

This was meaningful progress, but execution still existed through multiple
paths. A passing action could be recorded, yet a long-running task still depended
too heavily on the life of one process and its context window.

Lesson: bounded tools are necessary, but durable task continuity is a different
problem.

### September 2026: the durable execution ledger

The Execution Fabric established provider-neutral canonical records for:

- tasks
- attempts
- checkpoints
- ordered events
- terminal results
- authority references and provenance

Checkpoint state records the objective, success criteria, current plan,
completed and pending steps, findings, assumptions, decisions, artifacts,
actions, verification, errors, provider observations, and recommended next
action.

This removed the provider conversation from the role of canonical task memory.

The low point exposed by this work was also useful: a durable checkpoint alone
does not safely restart work. ARI still needed to know whether a worker was alive,
which attempt was current, and whether replacement was legitimate.

### September 2026: worker-session recovery

ARI added:

- leased worker sessions
- heartbeats
- deterministic stale-attempt classification
- linked replacement attempts under the same `task_id`
- continuation packets derived from canonical state
- replacement-worker acknowledgement
- explicit `execution_ready` state

Recovery deliberately stopped before executing the next side effect. This was a
safety choice, not an incomplete automatic retry disguised as success.

Lesson: a replacement worker can acknowledge state, but it cannot inherit the
right to act merely because it exists.

### October 2026: continuity gains an authority boundary

The recovered-action gateway added the missing boundary. For one recovered
pending action, ARI now:

1. Derives the proposed action from canonical state.
2. Revalidates task and attempt lifecycle, lease, session identity, pause,
   cancellation, blocking, authority, approval, restrictions, idempotency, and
   sandbox scope.
3. Persists its own allow, deny, require-approval, or blocked decision.
4. Checkpoints before dispatch.
5. Executes through the existing bounded tool machinery.
6. Persists the result before verification.
7. Verifies independently and checkpoints evidence.
8. Stops after one action and returns control to ARI.

Duplicate resume requests cannot repeat a completed effect. Actions with an
uncertain outcome are not blindly retried. A three-step recovered task executes
Step 2 while leaving Step 3 untouched until another ARI decision.

The verified suite reached 495 passing tests.

## Current architecture truth

Implemented:

- ARI-owned durable execution state
- current-backend worker recovery
- explicit continuation acknowledgement
- action-bound approval continuity
- one-action recovered execution authority
- idempotency and uncertain-effect protection
- verification evidence and read-only inspection

Partially converged:

- several legacy execution paths still use their earlier bounded controls
- execution-root configuration is enforced but not yet a first-class immutable
  authority object for every task
- API approval calls still depend on the surrounding service authentication
  boundary to prove the human actor

Not implemented:

- provider capability routing
- OpenAI-to-Anthropic or Anthropic-to-OpenAI failover
- Claude Code integration
- automatic local-model routing
- scheduler redesign
- PostgreSQL migration
- unrestricted autonomous continuation

## What comes next

### 1. Converge execution authority

Route one normal controller action through the same durable decision and
idempotency boundary used for recovered actions. Continue in small slices until
legacy execution entry points no longer bypass canonical authority.

### 2. Formalize the worker adapter contract

Separate normalized ARI task/checkpoint/result contracts from provider-specific
launch, tool, context, and usage details.

### 3. Add routing without provider ownership

Select workers by capability, availability, privacy, cost, tool access, and
context requirements. Model names remain adapter configuration, not architecture.

### 4. Add same-task provider failover

Use the existing task ID, checkpoint, continuation packet, acknowledgement,
authority snapshot, and result contract when a provider becomes unavailable.

### 5. Add local inference adapters

Support replaceable local runtimes only after their capabilities and tool
boundaries can satisfy the same contracts and evidence requirements.

## Standard for progress

ARI is not complete because an architecture is interesting or a model produces
good prose. A milestone counts when the behavior is durable, inspectable,
authority-preserving, tested, and honest about unresolved risk.
