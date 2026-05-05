# Coding Loop Native Skill Manifest

## Identity

- `skill_id`: `ari.native.coding_loop`
- Name: Coding Loop
- Status: first mature ARI-native skill
- Owner: ARI core execution spine

## Purpose

The coding loop lets ARI perform one bounded coding action, verify the result,
persist the lifecycle, ask for authority when needed, propose retries, execute
one approved retry at a time, inspect the chain, and capture compact memory.

The coding loop is not ARI itself. It is one native skill that proves how ARI
uses skills through the shared spine.

## Allowed Goal Types

The skill may accept goals that ask ARI to:

- inspect repository context
- read a file inside the execution root
- write explicitly bounded content to a file
- patch a known file with exact replacement text
- run allowlisted local verification or inspection commands
- perform one approval-aware coding-loop step
- inspect, approve, reject, propose, or advance an existing retry chain through
  established authority boundaries

## Capability Surface

- Plan one bounded coding action from a goal.
- Validate actions against repo context, execution root, tool registry, and
  command policy.
- Execute at most one validated action in the one-step loop.
- Persist coding-loop results.
- Persist execution runs when execution occurs.
- Create durable retry approval artifacts after retryable verification failure.
- Mutate retry approvals to approved or rejected.
- Execute exactly one durably approved retry proposal.
- Review retry execution outcomes.
- Decide whether a reviewed retry is eligible for one follow-up approval.
- Inspect retry chains with bounded depth and cycle detection.
- Capture compact chain lifecycle memory.

## Input Shape

Primary request:

- `goal`: natural-language or explicit bounded coding goal.
- `execution_root`: optional local root for bounded file/command access.
- `planner`: optional planner mode; defaults to the safe rule-based path unless
  another configured planner is explicitly selected.

Chain and approval requests:

- `coding_loop_result_id`: root result for chain inspection or chain-level
  convenience controls.
- `retry_approval_id`: durable retry approval artifact id.
- `approved_by`: actor granting approval.
- `rejected_by`: optional actor rejecting approval.
- `rejected_reason`: required reason for rejection.
- `max_depth`: bounded chain inspection depth.

## Output / Result Shape

Coding-loop result statuses:

- `success`
- `retryable_failure`
- `blocked`
- `unsafe`
- `ask_user`
- `requires_approval`

Common result references:

- `coding_loop_result_id`
- `preview_id`
- `execution_run_id`
- `retry_approval_id`
- `retry_execution_run_id`
- `next_retry_approval_id`

Chain results include:

- terminal chain status
- chain depth
- retry approvals in lineage order
- approval status for each approval
- retry execution run ids where present
- post-run review
- continuation decision
- truncation and cycle flags

## Authority Requirements

The coding loop must pause before executing any action marked
`requires_approval`.

Retry proposals require durable approval before execution. Approval mutation and
retry execution are separate boundaries. Chain-level controls are convenience
paths over the same durable approval artifacts, not new authority semantics.

## Approval Requirements

Supported approval states:

- `pending`
- `approved`
- `rejected`
- `not_required`

Rules:

- Pending retry approvals do not execute.
- Rejected retry approvals do not execute.
- Approved retry approvals execute at most once.
- Approval is never granted automatically.
- Chain advancement never approves anything.

## Validation Rules

Validation must reject:

- unknown action types
- plans with no actions
- overlarge plans
- multi-action plans in the one-step coding loop
- unsafe paths
- targets outside repo context when required
- unsafe commands
- non-allowlisted commands
- shell control tokens
- unsupported verification command shapes
- malformed retry or approval references
- truncated or cyclic chains for mutation/advancement

## Verification Methods

Current verification methods include:

- action success
- exact file content checks
- path existence checks
- action-level write and patch verification
- safe verification command policy checks for planner-proposed verification
  commands
- post-run retry execution review
- continuation decision after review

Verification evidence is persisted through `ExecutionRun`, coding-loop result,
retry approval, and chain inspection records.

## Execution Boundaries

The skill may operate only through ARI-owned execution paths:

- bounded execution root
- execution tool registry
- safe command policy
- execution controller
- durable approval boundary

It must not introduce broad shell access, arbitrary filesystem access, network
calls, autonomous loops, or background execution.

## Persistence Effects

The skill may persist:

- execution plan previews
- execution runs
- coding-loop results
- retry approval artifacts
- retry execution references
- post-run review summaries
- continuation and lineage references
- compact chain lifecycle memory blocks

It must store references and summaries rather than duplicating full execution
traces where canonical records already exist.

## Memory Effects

The skill may capture:

- execution-run summaries
- retry-approval execution summaries
- compact coding-loop chain lifecycle summaries

Memory capture is explanatory. It does not execute, approve, reject, advance, or
create retry proposals.

## Inspection Surfaces

Canonical inspection is available through existing CLI/API families for:

- plan previews
- execution runs
- coding-loop results
- retry approvals
- retry execution reviews
- continuation decisions
- retry chains
- chain advancement results
- chain-level approval mutation results
- chain-level next-approval proposal results
- memory capture and explanation

ACE may consume these surfaces later, but ACE must not own their logic.

## Failure Modes

- `blocked`: ARI cannot safely complete the requested action.
- `unsafe`: ARI detected a policy or validation boundary.
- `ask_user`: ARI needs clarification or a more bounded goal.
- `requires_approval`: ARI found a candidate action but authority is required.
- `retryable_failure`: execution occurred but verification failed in a way that
  can produce a bounded retry proposal.
- `exhausted`: lower-level execution ran out of allowed cycles.
- `unknown/incomplete`: chain inspection cannot produce a safe terminal story.

## Stop Conditions

The skill must stop when:

- one validated action has executed in the one-step loop
- one approved retry has executed during chain advancement
- verification passes
- approval is required
- the chain is pending, rejected, blocked, unsafe, ask-user, truncated, cyclic,
  stopped, or unknown
- no bounded plan can be produced
- validation fails
- max cycle or max inspection depth is reached

## Safety Constraints

- Fail closed on unsafe planner output.
- Never run model-proposed commands directly.
- Never approve automatically.
- Never execute pending or rejected approvals.
- Never execute an approved retry more than once.
- Never execute more than one retry per advancement call.
- Never bypass repo/path safety.
- Never bypass command policy.
- Never create a second planner, executor, memory, approval, or inspection
  system.

## Appropriate Goals

- "Inspect the repo context and show the current bounded execution state."
- "Write file notes/proof.txt with hello."
- "Patch README.md replacing old phrase with new phrase."
- "Run one approval-aware coding-loop step for this bounded file update."
- "Show the retry chain for this coding-loop result."
- "Approve the latest pending retry approval in this chain."
- "Capture memory for this completed coding-loop chain."

## Inappropriate Goals

- "Autonomously fix the whole repo until everything passes."
- "Run any shell command needed."
- "Push to GitHub after fixing it."
- "Read my email and update the repo."
- "Create a background daemon that keeps coding."
- "Bypass approval and execute the retry."
- "Let the imported agent decide what to do."

## Current Non-Goals

The coding-loop skill does not provide:

- generic skill orchestration
- a runtime skill registry
- dynamic skill loading
- broad multi-step autonomy
- external integrations
- ACE UI ownership
- generic local-model control

Those are future ARI capabilities only after they can plug into the same shared
spine without weakening authority or inspectability.
