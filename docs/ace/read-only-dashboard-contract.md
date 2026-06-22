# ACE Read-Only Dashboard Contract

## Purpose

ACE needs a read-only dashboard contract so it can manifest ARI state without
becoming an authority layer. The first interface phase is diagnostic and
read-only because ARI's backend authority, execution, approval, inspection, and
memory spine must remain canonical before any interface gains control surfaces.

ACE must not own decisions, approvals, execution, memory, skill selection, or
learning. ACE consumes ARI state and helps the user inspect it.

## ACE Doctrine

- ACE is manifestation and interface only.
- ARI remains the brain and authority layer.
- ACE consumes ARI state; it does not create independent state.
- ACE may render, filter, inspect, and link to ARI records.
- ACE must not duplicate ARI business logic.
- ACE must not infer its own approval, execution, memory, or skill state.

## Dashboard Scope

The read-only dashboard may show:

- ARI status
- active/native skills
- skill inventory summary
- current coding-loop chains
- pending retry approvals
- latest execution runs
- recent memory summaries
- recent lifecycle lessons
- future self-documentation content seeds and demo plans
- next safe action candidates
- blocked or ask-user items
- system health and warnings

This scope is intentionally broader than the coding loop. The coding loop is
one skill inside ARI, not the whole dashboard.

## Required Read-Only Data Panels

### Overview

- Purpose: summarize current ARI state, latest activity, and outstanding
  attention items.
- Source of truth: ARI status, current architecture docs, execution inspection,
  memory summaries, and skill inventory.
- Likely source: `/execution/runs`, `/execution/coding-loop/results`,
  `/memory/blocks`, `docs/status/current-architecture.md`.
- Must not: decide priorities, approve work, execute actions, or create memory.

### Skills

- Purpose: show active native skills and candidate future skills.
- Source of truth: `docs/skills/skill-inventory.md`.
- Likely source: docs rendering or future read-only docs endpoint.
- Must not: dynamically load skills, enable skills, create skills, or mark a
  candidate as active.

### Approvals

- Purpose: show pending, approved, and rejected authority artifacts.
- Source of truth: ARI retry approval inspection and future canonical approval
  inspection surfaces.
- Likely source: `/execution/coding-loop/retry-approvals`.
- Must not: approve, reject, execute, or mutate approval state in the read-only
  phase.

### Coding-Loop Chains

- Purpose: show bounded coding-loop retry chains as inspectable stories.
- Source of truth: ARI chain inspection.
- Likely source: `/execution/coding-loop/results/{result_id}/chain`.
- Must not: advance chains, propose next approvals, approve latest approvals, or
  execute retries.

### Execution Runs

- Purpose: show recent execution runs, status, planner selection, and results.
- Source of truth: `ExecutionRun` persistence and inspection.
- Likely source: `/execution/runs` and `/execution/runs/{run_id}`.
- Must not: run goals, rerun commands, mutate files, or invoke tools.

### Memory / Learning

- Purpose: show recent memory blocks, lifecycle lessons, and explanations.
- Source of truth: canonical memory blocks and explanation surfaces.
- Likely source: `/memory/blocks`, `/memory/context`, `/explain/execution/{run_id}`,
  `/explain/coding-loop-retry-approvals/{approval_id}`,
  `/explain/coding-loop-chains/{result_id}`.
- Must not: create, edit, delete, or capture memory in the read-only phase.

### Next Safe Actions

- Purpose: show ARI-suggested safe next actions or blocked/ask-user items when
  those already exist in ARI state.
- Source of truth: coding-loop results, chain terminal status, continuation
  decisions, skill inventory, and future self-improvement records.
- Likely source: chain inspection, coding-loop result inspection, memory
  summaries, and future canonical planning records.
- Must not: choose an action for ARI, execute an action, or synthesize a hidden
  plan.

### System Health

- Purpose: show warnings about missing configuration, blocked surfaces, stale
  state, or unsafe/incomplete chains.
- Source of truth: ARI status and inspection records.
- Likely source: current architecture/status docs, execution inspection,
  memory/status endpoints, and future health endpoints.
- Must not: repair state, restart services, install dependencies, or suppress
  warnings without ARI authority.

## Allowed Interactions In First ACE Phase

Allowed:

- view
- filter
- inspect
- copy ids
- open chain details
- open memory summaries
- open explanations
- navigate between linked ARI records

Not allowed:

- approve
- reject
- execute
- advance chain
- create skills
- invoke tools
- mutate memory
- send emails or messages
- schedule anything
- change planner mode
- change approval state

## Future Control Phase

Approval and control actions may come later, but only by calling ARI backend
authority surfaces. Candidate future controls include:

- approve latest
- reject latest
- advance one approved step
- capture memory
- propose next approval

ACE must never implement its own approval logic. Control UI may only become a
thin interface over ARI-owned authority paths after read-only inspection is
stable and tested.

## Source-Of-Truth Mapping

- Skill inventory: `docs/skills/skill-inventory.md`.
- Skill contract: `docs/skills/ari-native-skill-contract.md`.
- Coding-loop manifest: `docs/skills/coding-loop-skill.md`.
- Self-documentation manifest: `docs/skills/self-documentation-skill.md`.
- Coding-loop result inspection: `/execution/coding-loop/results`.
- Retry approval inspection: `/execution/coding-loop/retry-approvals`.
- Chain inspection: `/execution/coding-loop/results/{result_id}/chain`.
- Execution run inspection: `/execution/runs`.
- Memory blocks and context: `/memory/blocks`, `/memory/context`.
- Memory explanations: `/explain/execution/{run_id}`,
  `/explain/coding-loop-retry-approvals/{approval_id}`,
  `/explain/coding-loop-chains/{result_id}`.
- Current architecture: `docs/status/current-architecture.md`.

## Interface Anti-Patterns

Reject:

- dashboard-only state
- ACE-owned decisions
- ACE-owned approval state
- ACE-owned memory
- UI buttons that bypass ARI
- coding-loop-only dashboard framing
- hidden auto-refresh mutations
- voice or ambient control before read-only inspection is stable
- external integrations controlled from ACE before ARI authority exists

## Readiness Gates Before Implementation

The dashboard can be built only when:

- source endpoints or surfaces are clear
- the read-only state contract is documented
- no ACE-owned authority is introduced
- the dashboard can operate without mutating ARI
- tests can prove backend surfaces remain canonical
- UI tests can prove read-only interactions do not call mutation endpoints
- future controls have explicit ARI authority endpoints before buttons exist

Until then, this document is the boundary: ACE may display ARI, but ARI remains
the only brain.
