# ARI Self-Documentation Native Skill Manifest v0

## Purpose

ARI needs a self-documentation skill so the system can turn its own activity
into factual build summaries, demos, explanations, and content packages without
outsourcing truth to ACE or to a disconnected marketing workflow.

This supports the larger ARI vision because a self-improving local-first brain
must be able to explain what it did, why it mattered, what changed, what is
still incomplete, and what can be shown safely. Content generation is part of
ARI's product strategy when it is grounded in real system state, tests, commits,
memory, and approved narrative framing.

This skill is not for hype. It must document real progress, produce useful
explanatory artifacts, and keep public claims aligned with actual ARI
capabilities.

## Skill Identity

- `skill_id`: `ari.native.self_documentation`
- Name: Self-Documentation
- Lifecycle status: candidate / designed
- Current implementation status: Stage 1 prototype
- Active today: no runtime registry entry; core content seed generation exists
- Relationship to coding-loop lifecycle memory: future inputs should include
  compact coding-loop chain lifecycle summaries, execution-run memories, docs,
  commits, and test results.

## Allowed Goal Types

The skill may eventually accept goals such as:

- summarize recent ARI build work
- generate a factual build log
- create a demo script
- create a shot list
- create a voiceover draft
- create TikTok, Reel, LinkedIn, or long-form post drafts
- create terminal demo commands
- create a content package outline
- identify visually demonstrable moments from execution chains
- turn lifecycle memory into reusable explanation patterns

## Disallowed Goal Types

The skill must reject or require clarification for goals that ask it to:

- fabricate progress
- claim ARI can do things it cannot do
- expose secrets, tokens, private paths, or private data unintentionally
- record the screen without approval
- publish publicly without approval
- edit or post social content without explicit user approval
- bypass ARI memory, approval, validation, or inspection systems
- summarize private material without an authority boundary
- use external services before ARI has approved integration boundaries

## Capability Surface By Maturity Level

### Stage 0: Docs-Only Manifest

- Status: current stage.
- Capability: define the skill contract and boundaries.
- Execution: none.

### Stage 1: Build-Event Summary / Content Seed Generation

- Capability: turn recent commits, tests, docs, execution runs, coding-loop
  lifecycle memory, and user-approved framing into content seeds.
- Execution: read-only local git inspection and summary generation only.
- Output examples: build-event summary, content seed, factual narrative outline.

### Stage 2: Demo Script And Shot-List Generation

- Capability: convert content seeds into demo scripts, shot lists, and
  voiceover drafts.
- Execution: no recording.
- Output examples: demo script, shot list, voiceover draft.

### Stage 3: Local Demo Command Generator

- Capability: propose terminal demo commands that reveal real ARI behavior.
- Execution: proposal only unless explicitly run through ARI authority paths.
- Output examples: terminal demo plan, command list, expected observations.

### Stage 4: Screen Capture Planning

- Capability: plan what should be recorded, what private data must be hidden,
  and what approvals are required.
- Execution: no recording.
- Output examples: recording plan, privacy checklist, shot timing.

### Stage 5: Local Recording / Clipping / Captions Package

- Capability: create local recording, clipping, caption, and asset package
  plans, then later produce them only through approval-gated local execution.
- Execution: future approval-gated local media work only.
- Output examples: local clips, captions, thumbnails, export files.

### Stage 6: Export-Ready Social Package

- Capability: assemble platform-specific drafts and media packages.
- Execution: local export only with approval.
- Output examples: TikTok/Reel package, LinkedIn post package, long-form demo
  package.

### Stage 7: Approval-Gated Publishing Workflow

- Capability: propose publishing steps and track approval state.
- Execution: no public posting without explicit approval and future approved
  integrations.
- Output examples: approved publishing packet, posting checklist, final review
  artifact.

## Authority Requirements

- Read-only summarization is the default.
- Approval is required before recording the screen.
- Approval is required before exporting public-facing media.
- Approval is required before publishing or posting.
- Approval is required before including personal, sensitive, or private data.
- Approval is required before using external services or uploads.
- Approval is required before running generated demo commands that mutate state.

## Validation Rules

Generated content must be grounded in:

- actual commits
- test results
- execution runs
- coding-loop chains
- memory lifecycle summaries
- docs
- user-approved narrative framing

The skill must reject content requests when it cannot identify enough evidence
to support the claim.

## Verification Methods

Generated content should be checked against:

- commit hashes
- test outputs
- actual ARI capabilities
- current skill inventory
- current architecture/status docs
- no-secret and no-private-data policy
- no false or inflated claims
- user-approved narrative framing

Verification should produce evidence notes that explain which facts support the
draft.

## Memory Effects

The skill may create compact memory for:

- build-event summaries
- content seeds
- demo ideas
- audience and narrative preferences
- reusable explanation patterns
- approved public-facing claims

It must not duplicate full execution traces, full transcript logs, full screen
recordings, or unredacted private context when references and summaries are
sufficient.

## Inspection Payload

Future outputs should be inspectable as:

- `content_seed`
- `demo_script`
- `shot_list`
- `voiceover_draft`
- `social_post_draft`
- `content_package`
- `recording_plan`

Each payload should include:

- source references
- evidence summary
- intended audience or platform
- authority requirements
- privacy risks
- verification status
- created_at timestamp

## Safety Constraints

- No secret leakage.
- No accidental API key, token, path, or private-data exposure.
- No public posting without approval.
- No inflated capability claims.
- No recording of private data without approval.
- No external uploads by default.
- No fabricated demos.
- No editing that makes ARI appear to have done work it did not do.
- No ACE-owned truth layer for content claims.

## Relationship To ACE

ACE may display self-documentation outputs. ACE may help present scripts, clips,
shot lists, content packages, and approval state.

ACE must not own:

- content truth
- recording approval
- publishing approval
- ARI memory
- claim verification
- skill selection
- external posting logic

ARI remains the source of truth for what happened, what can be claimed, what
requires approval, and what has been verified.

## Relationship To Future Content Workflow

The intended pipeline is:

```text
ARI activity
-> build-event summary
-> content seed
-> demo script
-> shot list
-> recording plan
-> clip/caption package
-> approval
-> export/post
```

Each step must remain inspectable, evidence-backed, and authority-gated when it
touches recording, export, publishing, private data, or external services.

## Appropriate First Implementation

The first implementation should capture recent ARI work into a content seed
from:

- git commits
- tests
- docs
- coding-loop lifecycle memory

It should not record the screen, edit video, generate voice, export social
assets, post publicly, or connect external services.

The first implementation should prove:

- content seeds are grounded in actual ARI evidence
- no private data is included by default
- output is inspectable
- memory effects are compact
- no ACE-owned truth layer is introduced

Stage 1 readiness is defined in
`docs/skills/self-documentation-stage-1-readiness.md`.

The first Stage 1 implementation provides a local, deterministic `ContentSeed`
generator from a git commit range, exposed through
`api self-doc seed from-commits --from <hash> --to <hash> --json`. It does not
persist, record, edit, export, publish, upload, or call external services.
