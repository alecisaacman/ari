# ACE Read-Only Dashboard Read Model

## Purpose

This document defines the first read-only data model for ACE.

ACE is the interface and manifestation layer. ARI remains the brain and authority layer.

The first ACE dashboard must be diagnostic and read-only. It should help the user see what ARI knows, what ARI has done, what is waiting for approval, what is blocked, and what ARI recommends inspecting next.

The dashboard must not own decisions, approvals, execution, memory, skill selection, or independent state.

## Core Rule

ACE consumes ARI state.

ACE does not create ARI state.

ACE does not approve, reject, execute, advance chains, mutate memory, create skills, invoke tools, or decide what ARI should do next.

## Minimum Viable Dashboard

The first ACE dashboard should include:

1. Overview
2. Skills
3. Pending approvals
4. Coding-loop chains
5. Memory and lifecycle lessons
6. System health

No control buttons should exist in the first version.

---

## Panel 1: Overview

### User-facing purpose

Give the user a compact status snapshot of ARI.

### Required data

- ARI status
- latest activity
- pending approvals count
- blocked / ask-user count
- latest memory lesson
- system health summary

### Source of truth

ARI backend state, execution inspection, memory summaries, and current architecture/status docs.

### Existing surface status

Partial.

### Existing surfaces

- Execution result inspection
- Coding-loop chain inspection
- Retry approval inspection
- Memory explanation surfaces

### Missing read-only surface

A unified `overview` read model does not yet exist.

### Future endpoint/function

Potential future core function:

```text
get_ari_overview()
```

Potential future API endpoint:

```text
GET /ari/overview
```

### Must-not-own state warning

ACE must not compute independent status. It may format ARI status, but ARI must own the source data.

### Priority

P0.

---

## Panel 2: Skills

### User-facing purpose

Show what skills ARI currently has and what skills are candidates for future work.

### Required data

- Active native skills
- Candidate skills
- Skill lifecycle status
- Skill manifest links
- Readiness gates

### Source of truth

- `docs/skills/skill-inventory.md`
- `docs/skills/ari-native-skill-contract.md`
- `docs/skills/coding-loop-skill.md`

### Existing surface status

Partial.

### Existing surfaces

Docs exist. Runtime/API skill inventory does not yet exist.

### Missing read-only surface

No runtime skill inventory endpoint exists yet.

### Future endpoint/function

Potential future core function:

```text
list_ari_skills()
```

Potential future API endpoint:

```text
GET /skills
```

### Must-not-own state warning

ACE must not invent skill status. If a skill is not declared by ARI, ACE must not display it as active.

### Priority

P0.

---

## Panel 3: Approvals

### User-facing purpose

Show what requires user or operator authority before ARI may continue.

### Required data

- Pending retry approvals
- Approved approvals
- Rejected approvals
- Approval lineage
- Latest pending approval in a chain
- Approval reason
- Approval status
- Linked coding-loop result
- Linked execution run if available

### Source of truth

Durable retry approval registry and chain inspection.

### Existing surface status

Ready.

### Existing surfaces

Likely existing surfaces include:

```text
api execution retry-approvals list
api execution retry-approvals show --id <approval_id>
api execution coding-loops chain --id <coding_loop_result_id>
```

### Missing read-only surface

A dashboard-shaped approval summary may still be missing.

### Future endpoint/function

Potential future core function:

```text
list_pending_approvals()
```

Potential future API endpoint:

```text
GET /approvals/pending
```

### Must-not-own state warning

ACE must not own approval state. Approval state must remain durable in ARI.

### Priority

P0.

---

## Panel 4: Coding-Loop Chains

### User-facing purpose

Show the full story of a bounded coding-loop chain.

### Required data

- Recent coding-loop results
- Root coding-loop result id
- Original goal
- Initial status
- Terminal chain status
- Chain depth
- Retry approvals
- Retry executions
- Post-run reviews
- Continuation decisions
- Next pending approval if present
- Latest available safe action

### Source of truth

Durable coding-loop result store, retry approval registry, execution run persistence, and chain inspection.

### Existing surface status

Ready.

### Existing surfaces

Likely existing surfaces include:

```text
api execution coding-loops list
api execution coding-loops show --id <result_id>
api execution coding-loops chain --id <result_id>
```

### Missing read-only surface

A dashboard-specific recent-chain summary may be useful later, but is not required for v1.

### Future endpoint/function

Potential future API endpoint:

```text
GET /execution/coding-loop/chains/recent
```

### Must-not-own state warning

ACE must not reconstruct chain state independently if ARI already exposes chain inspection. ACE should display ARI’s chain payload.

### Priority

P0.

---

## Panel 5: Execution Runs

### User-facing purpose

Show what ARI actually executed and what happened.

### Required data

- Recent execution runs
- Run status
- Run reason
- Linked goal
- Linked coding-loop result if available
- Linked retry approval if available
- Verification result summary

### Source of truth

ExecutionRun persistence and execution inspection surfaces.

### Existing surface status

Partial.

### Existing surfaces

Execution run show/list surfaces may exist, but dashboard-specific linkage may need hardening.

### Missing read-only surface

A clear recent execution run summary endpoint may be needed.

### Future endpoint/function

Potential future API endpoint:

```text
GET /execution/runs/recent
```

### Must-not-own state warning

ACE must not infer execution success from file changes or UI state. ARI’s ExecutionRun remains authoritative.

### Priority

P1.

---

## Panel 6: Memory / Learning

### User-facing purpose

Show what ARI learned from activity.

### Required data

- Recent memory blocks
- Coding-loop lifecycle summaries
- Retry execution explanations
- Lessons / durable takeaways
- Improvement signals
- Memory source references

### Source of truth

ARI memory modules and memory explanation surfaces.

### Existing surface status

Partial.

### Existing surfaces

Likely existing surfaces include memory capture and explanation commands for coding-loop chains.

### Missing read-only surface

A recent lifecycle lesson list may be needed.

### Future endpoint/function

Potential future API endpoint:

```text
GET /memory/lifecycle-lessons/recent
```

### Must-not-own state warning

ACE must not write memory. It may display memory summaries generated by ARI.

### Priority

P0 for recent lifecycle lessons. P1 for deeper memory browsing.

---

## Panel 7: Next Safe Actions

### User-facing purpose

Show what the user could safely inspect or decide next.

### Required data

- Pending approvals
- Ask-user items
- Blocked items
- Executable approved retry available
- Propose-next eligible chain
- Capture-memory eligible chain
- Recommended inspection target

### Source of truth

ARI chain inspection, approval registry, continuation policy, and memory capture eligibility.

### Existing surface status

Partial.

### Missing read-only surface

ARI does not yet appear to expose a single next-safe-action read model.

### Future endpoint/function

Potential future core function:

```text
get_next_safe_actions()
```

Potential future API endpoint:

```text
GET /ari/next-safe-actions
```

### Must-not-own state warning

ACE may display next safe actions only if ARI produces them. ACE must not rank or invent them independently.

### Priority

P1.

---

## Panel 8: System Health

### User-facing purpose

Show whether ARI’s local system is healthy enough to trust.

### Required data

- API status
- database status
- current branch
- working tree state
- latest test status if available
- schema readiness
- stale docs warnings
- failed task warnings

### Source of truth

ARI system status, local repo state, test records, and status docs.

### Existing surface status

Missing / partial.

### Missing read-only surface

No canonical system health read model is defined yet.

### Future endpoint/function

Potential future endpoint:

```text
GET /system/health
```

### Must-not-own state warning

ACE must not declare ARI healthy without backend confirmation.

### Priority

P1.

---

## Readiness Summary

### Ready now

- Coding-loop chain inspection
- Retry approval inspection
- Coding-loop result inspection
- Skill docs
- Memory lifecycle capture / explanation for coding-loop chains

### Partial

- Overview
- Skills as runtime data
- Execution run summaries
- Memory lesson summaries
- Next safe actions

### Missing

- Unified ARI overview read model
- Runtime skill inventory endpoint
- Recent lifecycle lessons endpoint
- Next safe actions endpoint
- System health endpoint

### Should not be built yet

- Control dashboard
- Approval buttons
- Execution buttons
- Memory mutation UI
- Skill creation UI
- Voice control
- Ambient autonomous suggestions
- Email/calendar controls

---

## First Dashboard v1 Recommendation

The first dashboard should include only read-only panels:

1. Overview
2. Skills
3. Pending approvals
4. Recent coding-loop chains
5. Recent memory / lifecycle lessons

The first dashboard should not include controls.

The first dashboard should not mutate ARI.

The first dashboard should not own independent state.

---

## Future Control Phase

A later ACE control phase may expose actions such as:

- approve latest pending approval
- reject latest pending approval
- advance one approved step
- propose next pending approval
- capture lifecycle memory

Those controls must call ARI backend authority surfaces. ACE must not implement approval, execution, or memory logic itself.

---

## Interface Anti-Patterns

Do not build:

- dashboard-only state
- ACE-owned approval state
- ACE-owned memory
- ACE-owned planner decisions
- UI buttons that bypass ARI
- coding-loop-only dashboard framing
- voice/ambient control before read-only inspection is stable
- imported tool panels that bypass ARI authority

---

## Readiness Gates Before Implementation

A read-only ACE dashboard may be implemented only when:

- source-of-truth surfaces are identified
- the dashboard can operate without mutating ARI
- ARI owns all state shown in the dashboard
- missing read models are explicitly documented
- the dashboard is framed as ACE manifestation, not ARI brain
- tests can prove backend surfaces remain canonical
