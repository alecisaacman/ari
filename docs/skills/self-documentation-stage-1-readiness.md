# Self-Documentation Stage 1 Readiness

## Purpose

Stage 1 exists to capture real ARI progress as compact, factual content seeds.
It prevents content from being fabricated, preserves proof points, creates
reusable narrative material, and prepares for later demo, video, and social
automation without introducing recording, publishing, or external integrations.

Stage 1 is build-event summary / content seed generation only.

## Inputs

Accepted inputs:

- git commit range
- commit messages
- changed files
- test outputs
- docs updates
- coding-loop lifecycle memory
- execution chain summaries
- user-supplied framing
- redaction notes

Inputs should be treated as evidence. If evidence is missing, the content seed
must say so instead of inventing progress.

## Output: ContentSeed

Target output shape:

- `seed_id`
- `source_commit_range`
- `source_files`
- `title`
- `one_sentence_summary`
- `why_it_matters`
- `proof_points`
- `demo_idea`
- `hook_options`
- `visual_moments`
- `suggested_voiceover`
- `suggested_linkedin_post`
- `suggested_short_caption`
- `risk_notes`
- `redaction_notes`
- `claims_to_avoid`
- `next_content_angle`
- `created_at`

The `ContentSeed` is not a final post. It is a grounded, inspectable seed that
can later become a demo script, TikTok/Reel hook, LinkedIn post, shot list,
voiceover draft, or terminal demo plan.

## Grounding Requirements

Content seeds must be grounded in:

- actual commits
- actual test results
- actual docs
- actual execution outputs
- actual ARI capabilities

No seed may claim unfinished capabilities as completed. Candidate, designed,
prototype, active, and blocked states must be named accurately.

## Redaction And Safety Checklist

Before a seed is stored, exported, or reused, it must check for:

- API keys
- environment variables
- private paths
- emails
- personal data
- tokens
- internal-only repo details
- misleading capability claims
- overstatement of autonomy

If risk is present, the seed should include `risk_notes`, `redaction_notes`, and
`claims_to_avoid`.

## Authority Requirements

Stage 1 is read-only by default.

Approval is required before:

- recording screen
- exporting public media
- posting publicly
- uploading externally
- including sensitive data
- using user voice or AI voice clone

Stage 1 does not perform those actions. It only records the future authority
requirements.

## Verification Requirements

A content seed should be verifiable by:

- commit hashes
- test command outputs
- changed file references
- ARI memory references
- user-approved narrative framing

The seed should preserve enough references for ARI or the user to audit each
claim later.

## First Implementation Boundary

The first implementation now only:

- read a commit range or recent build summary
- generate a content seed
- generate a read-only content package from an existing content seed
- return a JSON-serializable seed object
- avoid recording
- avoid publishing
- avoid external uploads

It must not record the screen, generate voice, edit video, export media,
publish publicly, or call external integrations.

## CLI/API Future Surface

Implemented read-only CLI:

- `api self-doc seed from-commits --from <hash> --to <hash> --json`

Possible future commands:

- `api self-doc seed latest --limit <n>`
- `api self-doc seed show --id <seed_id>`

The future commands require persistence first and are not implemented by this
readiness doc.

## Relationship To ACE

ACE may display content seeds.

ACE must not:

- fabricate content
- approve content
- record screen
- export media
- post content
- mutate ARI memory
- own claim verification

ACE presents ARI-generated, ARI-grounded content artifacts. ARI remains the
source of truth.

## Implementation Readiness Checklist

- [x] Source data available.
- [x] Redaction rules defined.
- [x] Seed schema defined.
- [ ] Storage target decided.
- [x] Verification rules defined.
- [x] Tests planned.
- [x] No external upload path.
- [x] Approval boundaries defined.

## Anti-Patterns

Reject:

- fake demos
- exaggerated claims
- black-box content generation
- posting without approval
- recording private screens
- copying raw logs into public captions
- turning ARI into a content bot instead of a self-documenting brain
