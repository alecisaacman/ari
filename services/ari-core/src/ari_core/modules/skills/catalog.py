from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class SkillManifest:
    skill_id: str
    name: str
    lifecycle_status: str
    implementation_status: str
    purpose: str
    allowed_goal_patterns: tuple[str, ...]
    capability_summary: tuple[str, ...]
    authority_boundary: str
    verification_expectation: str
    memory_effect_expectation: str
    inspection_surfaces: tuple[str, ...]
    safety_constraints: tuple[str, ...]
    docs_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


SKILL_CATALOG: dict[str, SkillManifest] = {
    "ari.native.coding_loop": SkillManifest(
        skill_id="ari.native.coding_loop",
        name="Coding Loop",
        lifecycle_status="active",
        implementation_status="bounded authority spine implemented",
        purpose=(
            "Perform bounded coding work through ARI validation, execution, verification, "
            "approval, inspection, and memory."
        ),
        allowed_goal_patterns=(
            "write file",
            "patch",
            "fix failing",
            "unit test",
            "pytest",
            "ruff",
            "inspect recent code",
            "code changes",
            "repo",
            "repository",
            "implementation",
            "refactor",
            "bug",
        ),
        capability_summary=(
            "bounded repository inspection",
            "bounded file write or patch proposal",
            "unit-test or ruff-backed verification",
            "approval-aware retry chain",
        ),
        authority_boundary=(
            "Must use ARI execution validation, safe command policy, and approval boundaries "
            "before mutation or approved retry execution."
        ),
        verification_expectation=(
            "Verify with existing bounded execution results and allowed local test/lint commands."
        ),
        memory_effect_expectation=(
            "Capture compact coding-loop lifecycle memory only after an inspected chain outcome."
        ),
        inspection_surfaces=(
            "api execution coding-loop",
            "api execution coding-loops",
            "api execution retry-approvals",
            "api memory explain coding-loop-chain",
        ),
        safety_constraints=(
            "No arbitrary shell access.",
            "No automatic approval.",
            "No multi-step unattended autonomy.",
            "No bypass of command policy or execution validation.",
        ),
        docs_refs=(
            "docs/skills/coding-loop-skill.md",
            "docs/skills/ari-native-skill-contract.md",
        ),
    ),
    "ari.native.self_documentation": SkillManifest(
        skill_id="ari.native.self_documentation",
        name="Self-Documentation",
        lifecycle_status="prototype",
        implementation_status="content seed and content package generation implemented",
        purpose=(
            "Turn real ARI activity into factual content seeds, scripts, shot lists, "
            "and content packages."
        ),
        allowed_goal_patterns=(
            "content seed",
            "content package",
            "demo script",
            "shot list",
            "voiceover",
            "linkedin post",
            "tiktok",
            "reel",
            "build summary",
            "recent commits",
            "last ari work",
            "self-documentation",
            "document its own build",
        ),
        capability_summary=(
            "content seed generation from local evidence",
            "content package planning from seed evidence",
            "demo script and shot-list drafting",
            "redaction and claims-to-avoid review",
        ),
        authority_boundary=(
            "Read-only by default; approval required before recording, exporting, posting, "
            "uploading, or including sensitive data."
        ),
        verification_expectation=(
            "Verify claims against commits, tests, docs, execution traces, and current "
            "skill status."
        ),
        memory_effect_expectation=(
            "May create compact content-planning summaries; must not duplicate full traces."
        ),
        inspection_surfaces=(
            "api self-doc seed from-commits",
            "api self-doc package from-seed-json",
        ),
        safety_constraints=(
            "No fabricated progress.",
            "No recording, export, upload, or publishing without approval.",
            "No secret or private-data disclosure.",
            "No claim beyond source evidence.",
        ),
        docs_refs=(
            "docs/skills/self-documentation-skill.md",
            "docs/skills/self-documentation-stage-1-readiness.md",
        ),
    ),
    "ari.native.file_organization": SkillManifest(
        skill_id="ari.native.file_organization",
        name="File Organization",
        lifecycle_status="candidate",
        implementation_status="not implemented",
        purpose="Inspect local files and propose safe organization actions.",
        allowed_goal_patterns=("downloads folder", "organize files", "file organize"),
        capability_summary=("local file organization", "dry-run move or cleanup proposal"),
        authority_boundary=(
            "Approval required before broad filesystem traversal, moves, copies, or deletes."
        ),
        verification_expectation=(
            "Would require before/after manifests and reversible dry-run plans."
        ),
        memory_effect_expectation="Would store compact organization rationale and outcomes.",
        inspection_surfaces=("future file-organization inspection payload",),
        safety_constraints=(
            "No deletion without approval.",
            "No broad filesystem traversal without an authority boundary.",
            "No hidden file mutation.",
        ),
        docs_refs=("docs/skills/skill-inventory.md",),
    ),
    "ari.native.document_processing": SkillManifest(
        skill_id="ari.native.document_processing",
        name="Document Processing",
        lifecycle_status="candidate",
        implementation_status="not implemented",
        purpose="Extract, summarize, transform, and verify document or PDF files.",
        allowed_goal_patterns=("pdf", "docx", "this document", "document file"),
        capability_summary=("document or PDF summarization", "document extraction"),
        authority_boundary=(
            "Approval required before exposing, exporting, or mutating private documents."
        ),
        verification_expectation=(
            "Would require extracted-text evidence, file references, and readback checks."
        ),
        memory_effect_expectation="Would store compact document summary references only.",
        inspection_surfaces=("future document-processing inspection payload",),
        safety_constraints=(
            "No private document disclosure without approval.",
            "No source-file mutation without approval.",
            "No unsupported summary claims.",
        ),
        docs_refs=("docs/skills/skill-inventory.md",),
    ),
    "ari.native.research_gathering": SkillManifest(
        skill_id="ari.native.research_gathering",
        name="Research Gathering",
        lifecycle_status="candidate",
        implementation_status="not implemented",
        purpose="Gather sources, summarize findings, and create cited research briefs.",
        allowed_goal_patterns=("research", "sources", "citations", "brief"),
        capability_summary=("source gathering", "cited research brief generation"),
        authority_boundary="Approval required before external network access or paid services.",
        verification_expectation=(
            "Would require citations, retrieval metadata, and confidence notes."
        ),
        memory_effect_expectation="Would store compact cited findings and source references.",
        inspection_surfaces=("future research inspection payload",),
        safety_constraints=(
            "No external browsing without approval.",
            "No uncited factual claims.",
            "No quote-limit violations.",
        ),
        docs_refs=("docs/skills/skill-inventory.md",),
    ),
    "ari.native.spreadsheet_analysis": SkillManifest(
        skill_id="ari.native.spreadsheet_analysis",
        name="Spreadsheet Analysis",
        lifecycle_status="candidate",
        implementation_status="not implemented",
        purpose="Analyze tabular files, compute summaries, and produce verified outputs.",
        allowed_goal_patterns=("spreadsheet", "xlsx", "csv", "table analysis"),
        capability_summary=("tabular analysis", "formula and chart verification"),
        authority_boundary="Approval required before modifying source sheets or exporting files.",
        verification_expectation="Would require formula/readback checks and row/column validation.",
        memory_effect_expectation="Would store compact analysis summaries and source references.",
        inspection_surfaces=("future spreadsheet-analysis inspection payload",),
        safety_constraints=(
            "No source-sheet mutation without approval.",
            "No unsupported data claims.",
            "No unverified derived outputs.",
        ),
        docs_refs=("docs/skills/skill-inventory.md",),
    ),
    "ari.native.email_calendar_triage": SkillManifest(
        skill_id="ari.native.email_calendar_triage",
        name="Email And Calendar Triage",
        lifecycle_status="candidate",
        implementation_status="not implemented",
        purpose=(
            "Summarize inbox/calendar state and propose replies, scheduling actions, "
            "or follow-ups."
        ),
        allowed_goal_patterns=("email", "calendar", "meeting", "inbox", "schedule"),
        capability_summary=("email triage", "calendar triage", "drafted follow-up proposals"),
        authority_boundary=(
            "Explicit approval required before reading connected accounts, sending messages, "
            "modifying events, or storing private content."
        ),
        verification_expectation="Would require connector readback and no-send/no-mutate dry runs.",
        memory_effect_expectation="Would store compact action summaries only with approval.",
        inspection_surfaces=("future email-calendar inspection payload",),
        safety_constraints=(
            "No account access without approval.",
            "No sending or scheduling without approval.",
            "No hidden storage of private communication.",
        ),
        docs_refs=("docs/skills/skill-inventory.md",),
    ),
    "ari.native.browser_inspection": SkillManifest(
        skill_id="ari.native.browser_inspection",
        name="Browser Inspection",
        lifecycle_status="candidate",
        implementation_status="not implemented",
        purpose="Inspect web or local browser state for evidence and debugging.",
        allowed_goal_patterns=("browser", "web page", "localhost", "screenshot"),
        capability_summary=("browser state inspection", "page evidence capture"),
        authority_boundary=(
            "Approval required before external browsing, login/session use, form submission, "
            "downloads, or state mutation."
        ),
        verification_expectation=(
            "Would require URL/title snapshots and no-click/no-submit dry runs."
        ),
        memory_effect_expectation="Would store compact browser evidence references only.",
        inspection_surfaces=("future browser-inspection payload",),
        safety_constraints=(
            "No form submission without approval.",
            "No login/session use without approval.",
            "No external browsing by default.",
        ),
        docs_refs=("docs/skills/skill-inventory.md",),
    ),
    "ari.native.self_improvement_task_generation": SkillManifest(
        skill_id="ari.native.self_improvement_task_generation",
        name="Self-Improvement Task Generation",
        lifecycle_status="candidate",
        implementation_status="not implemented",
        purpose="Convert repeated failures or capability gaps into inspectable improvement tasks.",
        allowed_goal_patterns=("improvement task", "capability gap", "repeated failure"),
        capability_summary=("gap detection", "improvement task proposal"),
        authority_boundary=(
            "Approval required before queueing implementation or dispatching a builder."
        ),
        verification_expectation=(
            "Would require deduped evidence, priority rationale, and completion criteria."
        ),
        memory_effect_expectation=(
            "Would store compact improvement opportunities and evidence links."
        ),
        inspection_surfaces=("future self-improvement task inspection payload",),
        safety_constraints=(
            "No automatic implementation dispatch.",
            "No duplicate task spam.",
            "No hidden priority changes.",
        ),
        docs_refs=("docs/skills/skill-inventory.md",),
    ),
    "ari.native.planner_quality_goal_decomposition": SkillManifest(
        skill_id="ari.native.planner_quality_goal_decomposition",
        name="Planner Quality Goal Decomposition",
        lifecycle_status="candidate",
        implementation_status="not implemented",
        purpose="Break broad goals into bounded skill invocations and safe next actions.",
        allowed_goal_patterns=("decompose goal", "break down goal", "plan this project"),
        capability_summary=("bounded goal decomposition", "skill-fit rationale"),
        authority_boundary=(
            "Approval required before invoking skills with side effects or escalating to "
            "external models."
        ),
        verification_expectation=(
            "Would require bounded decomposition records and rejected alternatives."
        ),
        memory_effect_expectation="Would store compact decomposition rationale and outcomes.",
        inspection_surfaces=("future planner-quality inspection payload",),
        safety_constraints=(
            "No broad autonomy.",
            "No execution from decomposition alone.",
            "No second planner brain.",
        ),
        docs_refs=("docs/skills/skill-inventory.md",),
    ),
}

ACTIVE_SKILL_IDS = ("ari.native.coding_loop",)
IMPLEMENTED_SKILL_IDS = ("ari.native.coding_loop", "ari.native.self_documentation")


def get_skill_manifest(skill_id: str) -> SkillManifest | None:
    return SKILL_CATALOG.get(skill_id)


def list_skill_manifests() -> tuple[SkillManifest, ...]:
    return tuple(SKILL_CATALOG.values())
