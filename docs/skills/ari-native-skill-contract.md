# ARI Native Skill Contract v0

## Purpose

An ARI-native skill is a bounded capability that lets ARI pursue a class of
goals through the canonical ARI spine: memory, authority, validation,
execution, verification, persistence, inspection, explanation, and learning.

The coding loop is the first native skill because it proves the spine can turn
a goal into a grounded action, validate it, execute only within authority
boundaries, verify the result, persist the lifecycle, ask for approval, review
outcomes, propose retries, stop, and capture lessons.

This document is not a generic agent framework. It is a contract for preventing
future skills from becoming competing brains. Framework code should only appear
after at least one more skill proves these boundaries in practice.

## Non-Negotiable Doctrine

- ARI remains the brain: decision, memory, planning, execution, verification,
  learning, authority, self-improvement, and skill orchestration.
- ACE remains the interface: ambient presence, UI, voice, notifications,
  surfaces, and manifestation.
- A skill must never own canonical memory independently.
- A skill must never own approval semantics independently.
- A skill must never own execution policy independently.
- A skill must never bypass ARI validation, verification, persistence,
  inspection, explanation, or learning paths.
- A skill may contain domain-specific logic, but it must report decisions,
  authority requirements, results, and lessons through ARI.

## Required Skill Declaration

Every future ARI-native skill must declare:

- `skill_id`: stable identifier.
- `purpose`: what goal class the skill exists to handle.
- `allowed_goal_types`: natural-language or typed goal classes it may accept.
- `capability_surface`: operations the skill can propose or perform.
- `input_schema`: required and optional request fields.
- `output_result_schema`: result statuses, references, summaries, and payloads.
- `authority_requirements`: what requires user or operator authority.
- `approval_requirements`: pending, approved, rejected, or not-required states.
- `validation_rules`: local checks before any action or proposal is accepted.
- `verification_methods`: how outcomes are checked without trusting the action.
- `execution_boundaries`: files, commands, tools, networks, or resources allowed.
- `memory_effects`: what should be captured, summarized, ignored, or forgotten.
- `inspection_payload`: what CLI/API/ACE surfaces can read.
- `failure_modes`: blocked, unsafe, ask-user, retryable, exhausted, or failed.
- `stop_conditions`: when the skill must stop instead of continuing.
- `safety_constraints`: explicit fail-closed rules and prohibited behavior.

## Shared ARI Spine

Each skill must use the shared ARI spine:

- Memory: retrieve context and capture compact lifecycle lessons.
- Authority / approval: represent pending, approved, rejected, and not-required
  authority states through canonical approval concepts.
- Validation: reject unsafe or malformed plans before execution.
- Execution runtime: use ARI-owned bounded execution paths only.
- Verification: prove or classify outcomes through declared checks.
- Persistence: store lifecycle records in canonical durable stores.
- Inspection: expose state through canonical inspection payloads.
- Explanation: answer why ARI acted, stopped, asked, proposed, approved,
  rejected, executed, reviewed, or learned.
- Learning / self-improvement: turn repeated failure or high-leverage lessons
  into memory and future improvement candidates.

## What Remains Skill-Specific

Skill-specific logic is allowed when it describes the domain, not the brain.

For the coding loop, the skill-specific parts include:

- repo context
- file read/write/patch actions
- retry proposal construction from verification failure
- pytest and ruff verification hints
- repo/path safety assumptions
- coding-specific result classifications and chain language

Those pieces should not be copied directly into another skill. Future skills
should reuse the shared spine and replace only the domain-specific context,
actions, validation, verification, and memory summaries.

## Imported And Open-Source Skills

External skills, libraries, tools, and open-source frameworks may be wrapped by
ARI only as tools under ARI authority.

They must not:

- run as independent agents
- own a separate planner
- own a separate memory system
- own a separate approval model
- execute outside ARI policy
- persist uninspectable state
- call external services without an ARI-visible authority boundary

Wrappers must expose:

- capabilities
- input and output schemas
- risks
- required approvals
- validation hooks
- verification hooks
- memory effects
- inspection payloads

ARI may borrow useful tool implementations. It must not import a competing
brain.

## Candidate Future Skills

Good next candidates are skills with bounded inputs, clear verification, and
compact memory effects:

- Document and PDF processing: extract, summarize, transform, and verify files.
- Research gathering: collect sources, cite evidence, and store concise briefs.
- Local file organization: inspect and propose safe moves before mutation.
- Spreadsheet analysis: read tables, compute summaries, and verify outputs.
- Email/calendar triage later: summarize and propose actions behind approval.
- Browser inspection later: read pages or local app state without owning logic.

Communication, calendar, browser, and ambient skills should wait until the
authority, privacy, and inspection boundaries are explicit.

## Readiness Gates

ARI may add a new native skill only when:

- The existing ARI spine can support the skill without duplication.
- Authority requirements are explicit.
- Approval states are inspectable.
- Validation is deterministic and fail-closed.
- Verification methods are declared before execution is added.
- Memory effects are compact and useful.
- Inspection output is defined for CLI/API/ACE.
- Tests can prove the skill does not create a second brain.
- Tests can prove non-execution paths do not mutate state.
- Tests can prove unsafe inputs fail closed.

## Anti-Patterns

Reject these patterns:

- mini-agents hidden inside a skill
- unattended autonomy without explicit authority boundary
- skill-owned canonical memory
- skill-owned approval semantics
- skill-owned execution policy
- broad shell access
- UI-first skill work before backend authority exists
- external tools that bypass ARI validation or inspection
- long-lived state that cannot be explained
- planner upgrades that weaken validation or verification

## Next Implementation Implications

This contract should guide:

- a future skill registry
- the current read-only skill-selection prototype
- future skill manifests
- future local and open-source tool wrapping
- shared result and inspection vocabulary
- ACE dashboard consumption of skill state
- future memory compaction and self-improvement tasks

The next code work should extract only the smallest reusable pieces proven by
the coding loop. Until then, this contract is the boundary: future skills plug
into ARI; they do not become ARI.

The read-only skill-selection prototype may recommend an existing skill, ask
for clarification, identify a missing candidate skill, or block unsafe goals.
It must not execute skills, load skills dynamically, or become a separate
planner.

The first static manifest instance is `docs/skills/coding-loop-skill.md`.
The first designed candidate beyond the coding loop is
`docs/skills/self-documentation-skill.md`.
The current docs-only skill inventory is `docs/skills/skill-inventory.md`.
ACE read-only dashboard consumption is bounded by
`docs/ace/read-only-dashboard-contract.md`.
