import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from ...core.paths import DB_PATH
from ..coordination.db import get_coordination_entity, list_coordination_entities, put_coordination_entity
from ..memory.db import list_ari_memories
from ..networking.db import get_connection, initialize_database
from ..tasks.db import list_ari_tasks


class EscalationPacket(TypedDict):
    whyEscalationIsNeeded: str
    whatChanged: str
    availableOptions: List[str]
    recommendedAction: str
    exactQuestionForAlec: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compact_text(value: str, max_len: int = 96) -> str:
    normalized = " ".join((value or "").strip().split())
    if len(normalized) <= max_len:
        return normalized
    return f"{normalized[: max_len - 3]}..."


def parse_json_array(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, str)]


def parse_json_object(raw: Optional[str], fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not raw:
        return fallback
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    return parsed if isinstance(parsed, dict) else fallback


def parse_iso_sort(value: Optional[str]) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def bool_to_int(value: bool) -> int:
    return 1 if value else 0


def list_memories(memory_types: Optional[List[str]] = None, limit: int = 50, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    rows = list_ari_memories(memory_types=memory_types, limit=limit, db_path=db_path)
    return [
        {
            "id": str(row["id"]),
            "type": row["type"],
            "title": row["title"],
            "content": row["content"],
            "tags": parse_json_array(row["tags_json"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


def list_tasks(limit: int = 50, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    rows = list_ari_tasks(limit=limit, db_path=db_path)
    return [
        {
            "id": str(row["id"]),
            "title": row["title"],
            "status": row["status"],
            "notes": row["notes"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


def list_coordination(entity: str, limit: int = 100, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    rows = list_coordination_entities(entity, limit=limit, db_path=db_path)
    return [{key: row[key] for key in row.keys()} for row in rows]


def get_coordination(entity: str, identifier: str, db_path: Path = DB_PATH) -> Optional[Dict[str, Any]]:
    row = get_coordination_entity(entity, identifier, db_path=db_path)
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def store_awareness_snapshot(snapshot: Dict[str, Any], db_path: Path = DB_PATH) -> Dict[str, Any]:
    initialize_database(db_path=db_path)
    latest = get_latest_awareness_snapshot(db_path=db_path)
    if latest and latest["signature"] == snapshot["signature"]:
        refreshed = {
            **latest,
            "summary": snapshot["summary"],
            "currentFocus": snapshot["currentFocus"],
            "tracking": snapshot["tracking"],
            "recentIntent": snapshot["recentIntent"],
            "mode": snapshot["mode"],
        }
        return {"snapshot": refreshed, "changed": False}

    timestamp = snapshot["updatedAt"]
    with get_connection(db_path) as connection:
        connection.execute(
            """
            insert into ari_awareness_snapshots (
                id, mode, summary, current_focus_json, tracking_json, recent_intent_json, signature, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot["id"],
                snapshot["mode"],
                snapshot["summary"],
                json.dumps(snapshot["currentFocus"]),
                json.dumps(snapshot["tracking"]),
                json.dumps(snapshot["recentIntent"]),
                snapshot["signature"],
                timestamp,
            ),
        )
        connection.commit()
    return {"snapshot": snapshot, "changed": True}


def _row_to_awareness_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "mode": row["mode"],
        "summary": row["summary"],
        "currentFocus": json.loads(row["current_focus_json"]) if row.get("current_focus_json") else [],
        "tracking": json.loads(row["tracking_json"]) if row.get("tracking_json") else [],
        "recentIntent": json.loads(row["recent_intent_json"]) if row.get("recent_intent_json") else [],
        "signature": row["signature"],
        "updatedAt": row["created_at"],
    }


def get_latest_awareness_snapshot(db_path: Path = DB_PATH) -> Optional[Dict[str, Any]]:  # type: ignore[no-redef]
    if not db_path.exists():
        return None
    try:
        with get_connection(db_path) as connection:
            row = connection.execute(
                """
                select id, mode, summary, current_focus_json, tracking_json, recent_intent_json, signature, created_at
                from ari_awareness_snapshots
                order by created_at desc
                limit 1
                """
            ).fetchone()
    except Exception:
        return None
    return _row_to_awareness_snapshot({key: row[key] for key in row.keys()}) if row else None


def list_improvements(limit: int = 100, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    rows = list_coordination("self_improvement", limit=limit, db_path=db_path)
    mapped: List[Dict[str, Any]] = []
    for row in rows:
        mapped.append(
            {
                "id": row["id"],
                "capability": row["capability"],
                "missingCapability": row["missing_capability"],
                "whyItMatters": row["why_it_matters"],
                "whatItUnlocks": row["what_it_unlocks"],
                "smallestSlice": row["smallest_slice"],
                "nextBestAction": row["next_best_action"],
                "approvalRequired": bool(row["approval_required"]),
                "relativePriority": row["relative_priority"],
                "leverage": row["leverage_score"],
                "urgency": row["urgency_score"],
                "dependencyValue": row["dependency_value_score"],
                "autonomyImpact": row["autonomy_impact_score"],
                "implementationEffort": row["implementation_effort_score"],
                "priorityScore": row["priority_score"],
                "status": row["status"],
                "approvalId": row["approval_id"],
                "taskId": row["task_id"],
                "dedupeKey": row["dedupe_key"],
                "instructionOrchestrationId": row["instruction_orchestration_id"],
                "dispatchRecordId": row["dispatch_record_id"],
                "dispatchOrchestrationId": row["dispatch_orchestration_id"],
                "dispatchMode": row["dispatch_mode"],
                "dispatchEvidence": row["dispatch_evidence"],
                "consumedAt": row["consumed_at"],
                "consumer": row["consumer"],
                "completionOrchestrationId": row["completion_orchestration_id"],
                "completionEvidence": row["completion_evidence"],
                "verificationOrchestrationId": row["verification_orchestration_id"],
                "verificationEvidence": row["verification_evidence"],
                "reflection": parse_json_object(
                    row["reflection_json"],
                    {
                        "repeatedLimitations": 0,
                        "repeatedUserFriction": 0,
                        "repeatedManualSteps": 0,
                        "repeatedEscalationCauses": 0,
                        "total": 0,
                    },
                ),
                "firstObservedAt": row["first_observed_at"],
                "lastObservedAt": row["last_observed_at"],
                "approvedAt": row["approved_at"],
                "queuedAt": row["queued_at"],
                "dispatchedAt": row["dispatched_at"],
                "completedAt": row["completed_at"],
                "verifiedAt": row["verified_at"],
            }
        )
    return mapped


def get_top_improvement_focus(db_path: Path = DB_PATH) -> Optional[Dict[str, Any]]:
    items = list_improvements(limit=100, db_path=db_path)
    ordered = sorted(
        items,
        key=lambda item: (
            1 if item["status"] == "verified" else 0,
            -int(item["priorityScore"]),
            -parse_iso_sort(item["lastObservedAt"]),
        ),
    )
    for item in ordered:
        if item["status"] != "verified":
            return item
    return None


def status_rank(status: str) -> int:
    return {
        "proposed": 0,
        "approved": 1,
        "queued": 2,
        "dispatched": 3,
        "completed": 4,
        "verified": 5,
    }.get(status, 0)


def list_execution_outcomes(limit: int = 100, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    return [
        {
            "itemKey": row["item_key"],
            "itemType": row["item_type"],
            "itemId": row["item_id"],
            "title": row["title"],
            "state": row["state"],
            "stage": row["stage"],
            "stateSince": row["state_since"],
            "blockedReason": row["blocked_reason"],
            "failureReason": row["failure_reason"],
            "verificationSignal": row["verification_signal"],
            "nextAction": row["next_action"],
            "evidence": row["evidence_mode"],
            "updatedAt": row["updated_at"],
        }
        for row in list_coordination("execution_outcome", limit=limit, db_path=db_path)
    ]


def list_projects(limit: int = 20, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "goal": row["goal"],
            "completionCriteria": row["completion_criteria"],
            "status": row["status"],
            "source": row["source"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in list_coordination("project", limit=limit, db_path=db_path)
    ]


def list_milestones(project_id: str, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    rows = [row for row in list_coordination("project_milestone", limit=500, db_path=db_path) if row["project_id"] == project_id]
    return [
        {
            "id": row["id"],
            "projectId": row["project_id"],
            "title": row["title"],
            "status": row["status"],
            "completionCriteria": row["completion_criteria"],
            "sequence": row["sequence"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


def list_steps(project_id: str, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    rows = [row for row in list_coordination("project_step", limit=1000, db_path=db_path) if row["project_id"] == project_id]
    return [
        {
            "id": row["id"],
            "projectId": row["project_id"],
            "milestoneId": row["milestone_id"],
            "title": row["title"],
            "status": row["status"],
            "completionCriteria": row["completion_criteria"],
            "dependsOnStepIds": parse_json_array(row["depends_on_step_ids_json"]),
            "blockedBy": parse_json_array(row["blocked_by_json"]),
            "sequence": row["sequence"],
            "linkedTaskId": row["linked_task_id"],
            "linkedImprovementId": row["linked_improvement_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


def _put_project(project: Dict[str, Any], db_path: Path = DB_PATH) -> None:
    put_coordination_entity(
        "project",
        {
            "id": project["id"],
            "title": project["title"],
            "goal": project["goal"],
            "completion_criteria": project["completionCriteria"],
            "status": project["status"],
            "source": project["source"],
            "created_at": project["createdAt"],
            "updated_at": project["updatedAt"],
        },
        db_path=db_path,
    )


def _put_milestone(milestone: Dict[str, Any], db_path: Path = DB_PATH) -> None:
    put_coordination_entity(
        "project_milestone",
        {
            "id": milestone["id"],
            "project_id": milestone["projectId"],
            "title": milestone["title"],
            "status": milestone["status"],
            "completion_criteria": milestone["completionCriteria"],
            "sequence": milestone["sequence"],
            "created_at": milestone["createdAt"],
            "updated_at": milestone["updatedAt"],
        },
        db_path=db_path,
    )


def _put_step(step: Dict[str, Any], db_path: Path = DB_PATH) -> None:
    put_coordination_entity(
        "project_step",
        {
            "id": step["id"],
            "project_id": step["projectId"],
            "milestone_id": step["milestoneId"],
            "title": step["title"],
            "status": step["status"],
            "completion_criteria": step["completionCriteria"],
            "depends_on_step_ids_json": json.dumps(step["dependsOnStepIds"]),
            "blocked_by_json": json.dumps(step["blockedBy"]),
            "sequence": step["sequence"],
            "linked_task_id": step["linkedTaskId"],
            "linked_improvement_id": step["linkedImprovementId"],
            "created_at": step["createdAt"],
            "updated_at": step["updatedAt"],
        },
        db_path=db_path,
    )


def sync_project_focus(db_path: Path = DB_PATH) -> Optional[Dict[str, Any]]:
    project = list_projects(limit=1, db_path=db_path)[0] if list_projects(limit=1, db_path=db_path) else None
    if not project:
        return None

    milestones = list_milestones(project["id"], db_path=db_path)
    steps = list_steps(project["id"], db_path=db_path)
    tasks = {task["id"]: task for task in list_tasks(limit=200, db_path=db_path)}
    improvements = {item["id"]: item for item in list_improvements(limit=200, db_path=db_path)}
    outcomes = {f'{row["itemType"]}:{row["itemId"]}': row for row in list_execution_outcomes(limit=200, db_path=db_path)}
    completed_step_ids = set()

    for step in steps:
        linked_task = tasks.get(step["linkedTaskId"]) if step["linkedTaskId"] else None
        linked_improvement = improvements.get(step["linkedImprovementId"]) if step["linkedImprovementId"] else None
        if (linked_task and linked_task["status"] == "done") or (
            linked_improvement and linked_improvement["status"] == "verified"
        ):
            completed_step_ids.add(step["id"])

    for step in steps:
        next_status = step["status"]
        blocked_by: List[str] = []
        if step["id"] in completed_step_ids:
            next_status = "completed"
        else:
            for dependency_id in step["dependsOnStepIds"]:
                if dependency_id not in completed_step_ids:
                    dependency = next((item for item in steps if item["id"] == dependency_id), None)
                    blocked_by.append(
                        f'Waiting on {dependency["title"]}' if dependency else "Waiting on another step"
                    )
            execution_outcome = None
            if step["linkedTaskId"]:
                execution_outcome = outcomes.get(f'task:{step["linkedTaskId"]}')
            if not execution_outcome and step["linkedImprovementId"]:
                execution_outcome = outcomes.get(f'improvement:{step["linkedImprovementId"]}')
            if execution_outcome and execution_outcome["state"] == "blocked" and execution_outcome.get("blockedReason"):
                blocked_by.append(execution_outcome["blockedReason"])
            next_status = "blocked" if blocked_by else "ready"

        if next_status != step["status"] or blocked_by != step["blockedBy"]:
            step["status"] = next_status
            step["blockedBy"] = blocked_by
            step["updatedAt"] = now_iso()
            _put_step(step, db_path=db_path)

    refreshed_steps = list_steps(project["id"], db_path=db_path)
    for milestone in milestones:
        milestone_steps = [step for step in refreshed_steps if step["milestoneId"] == milestone["id"]]
        next_status = "pending"
        if milestone_steps and all(step["status"] == "completed" for step in milestone_steps):
            next_status = "completed"
        elif any(step["status"] in {"ready", "in_progress"} for step in milestone_steps):
            next_status = "active"
        elif any(step["status"] == "blocked" for step in milestone_steps):
            next_status = "blocked"
        if next_status != milestone["status"]:
            milestone["status"] = next_status
            milestone["updatedAt"] = now_iso()
            _put_milestone(milestone, db_path=db_path)

    final_milestones = list_milestones(project["id"], db_path=db_path)
    next_step = next((step for step in refreshed_steps if step["status"] == "ready"), None)
    blocked_step = next((step for step in refreshed_steps if step["status"] == "blocked"), None)
    major_blocker = blocked_step["blockedBy"][0] if blocked_step and blocked_step["blockedBy"] else None
    project_status = (
        "completed"
        if final_milestones and all(milestone["status"] == "completed" for milestone in final_milestones)
        else "blocked"
        if major_blocker and not next_step
        else "active"
    )
    if project_status != project["status"]:
        project["status"] = project_status
        project["updatedAt"] = now_iso()
        _put_project(project, db_path=db_path)
    refreshed_project = list_projects(limit=1, db_path=db_path)[0]
    current_milestone = next(
        (milestone for milestone in final_milestones if milestone["status"] != "completed"),
        None,
    )
    return {
        "project": refreshed_project,
        "currentMilestone": current_milestone,
        "nextStep": next_step,
        "majorBlocker": major_blocker,
        "completionCriteria": refreshed_project["completionCriteria"],
        "progressSummary": (
            f'{refreshed_project["title"]} is complete.'
            if project_status == "completed"
            else f'Next valid step: {next_step["title"]}.'
            if next_step
            else f"Progress is blocked by {major_blocker}."
            if major_blocker
            else f'{refreshed_project["title"]} is active.'
        ),
    }


ESCALATION_RULES = [
    {
        "key": "architecture",
        "pattern": ["architecture", "repo layout", "monorepo", "canonical repo", "source of truth", "bridge slice", "move into", "integration map"],
        "why": "The builder output changes architecture or source-of-truth boundaries.",
    },
    {
        "key": "identity",
        "pattern": ["identity", "ari vs ace", "branding", "primary identity", "hub feel", "core doctrine"],
        "why": "The builder output changes product identity or system framing.",
    },
    {
        "key": "security",
        "pattern": ["security", "privacy", "auth", "permission", "token", "secret", "public internet", "expose", "access control"],
        "why": "The builder output affects privacy, auth, or exposure risk.",
    },
    {
        "key": "policy",
        "pattern": ["autonomy policy", "irreversible", "delete", "reset", "destroy", "data loss", "permission scope"],
        "why": "The builder output changes autonomy or includes irreversible risk.",
    },
    {
        "key": "tradeoff",
        "pattern": ["tradeoff", "recommend", "options", "blocked", "decision needed", "should we", "meaningful risk"],
        "why": "The builder output contains a meaningful tradeoff or needs operator judgment.",
    },
]


def normalize_lines(raw: str) -> List[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def extract_highlights(lines: List[str]) -> List[str]:
    candidates = []
    for line in lines:
        lowered = line.lower()
        if (
            line.startswith("- ")
            or line.startswith("* ")
            or line[:2].isdigit()
            or any(token in lowered for token in ["passed", "failed", "error", "warning", "changed", "added", "updated", "removed", "created", "verified", "build", "test"])
        ):
            candidates.append(line[2:] if line.startswith(("- ", "* ")) else line)
    source = candidates if candidates else lines
    return source[:4]


def infer_focus(raw: str) -> str:
    lowered = raw.lower()
    if any(token in lowered for token in ["task", "approval", "activity feed", "background runtime", "orchestration"]):
        return "runtime coordination"
    if any(token in lowered for token in ["identity", "hub", "ui", "ace", "ari"]):
        return "hub identity"
    if any(token in lowered for token in ["auth", "session", "trigger", "phone", "lan"]):
        return "access and delivery"
    return "the next smallest planned slice"


def classify_builder_output(raw_output: str, current_priority: str = "", latest_decision: str = "") -> Dict[str, Any]:
    trimmed = raw_output.strip()
    lines = normalize_lines(trimmed)
    highlights = extract_highlights(lines)
    concise_summary = " ".join(highlights) if highlights else (trimmed[:220] if trimmed else "Builder output was received.")
    lowered = trimmed.lower()

    matched = [rule for rule in ESCALATION_RULES if any(token in lowered for token in rule["pattern"])]
    long_output = len(trimmed) > 900 or len(lines) > 14
    has_verification_density = any(token in lowered for token in ["npm test", "npm run build", "passed", "verified", "tests"]) and len(lines) > 6

    if matched:
        return {
            "classification": "escalate_to_alec",
            "conciseSummary": concise_summary,
            "nextInstruction": "",
            "reasoning": f'Escalated because the output matched: {", ".join(rule["key"] for rule in matched)}.',
            "escalationRequired": True,
            "escalationPacket": {
                "whyEscalationIsNeeded": " ".join(rule["why"] for rule in matched),
                "whatChanged": concise_summary,
                "availableOptions": [
                    "Approve the recommended direction and let builder continue.",
                    "Constrain scope and request a narrower implementation slice.",
                    "Hold here and revisit the decision manually.",
                ],
                "recommendedAction": "Review the recommendation, then either approve the direction or tighten scope before the next builder step.",
                "exactQuestionForAlec": f'Alec: builder output touched {matched[0]["key"]}. Do you want ARI to continue on this direction, narrow the slice, or hold for review?',
            },
        }

    focus = infer_focus(trimmed)
    reasoning = (
        "The output is substantial enough to summarize, but it does not require operator escalation."
        if long_output or has_verification_density
        else "The output looks routine and safe to pass through without escalation."
    )
    if current_priority:
        reasoning = f"{reasoning} Current priority: {current_priority}."
    if latest_decision:
        reasoning = f"{reasoning} Recent decision: {latest_decision}."
    next_instruction = (
        f"Use this as working state. Continue with the next smallest concrete slice in {focus}, keep one canon, and verify with focused checks before reporting back."
        if long_output or has_verification_density
        else f"Continue on {focus}. Keep scope tight, avoid drift, and report only the next meaningful state change."
    )
    if current_priority:
        next_instruction = f"{next_instruction} Stay aligned with this priority: {current_priority}."
    return {
        "classification": "auto_summarize" if (long_output or has_verification_density) else "auto_pass",
        "conciseSummary": concise_summary,
        "nextInstruction": next_instruction,
        "reasoning": reasoning,
        "escalationRequired": False,
    }


IMPROVEMENT_RULES = [
    {
        "capability": "interface-control",
        "keywords": ["interface", "ui", "click", "scroll", "tap", "control"],
        "triggers": ["click", "tap", "scroll", "control the interface", "control the ui", "direct interface control", "independent interface control", "use the interface"],
        "baseScores": {"leverage": 5, "urgency": 4, "dependencyValue": 5, "autonomyImpact": 5, "implementationEffort": 3},
    },
    {
        "capability": "artifact-generation",
        "keywords": ["artifact", "generate", "export", "pdf", "docx", "document", "image", "slides", "deck", "report"],
        "triggers": ["generate", "create", "export", "produce", "pdf", "docx", "document", "artifact", "report", "image", "deck", "slide", "slides"],
        "baseScores": {"leverage": 4, "urgency": 3, "dependencyValue": 4, "autonomyImpact": 4, "implementationEffort": 3},
    },
    {
        "capability": "notification-delivery",
        "keywords": ["notification", "notify", "alert", "phone", "browser"],
        "triggers": ["push notification", "browser notification", "notify me", "iphone notification", "phone notification", "alert me"],
        "baseScores": {"leverage": 4, "urgency": 3, "dependencyValue": 3, "autonomyImpact": 4, "implementationEffort": 2},
    },
]


def clamp_count(value: int) -> int:
    if value <= 0:
        return 0
    return min(int(round(value)), 4)


def count_trigger_matches(values: List[str], triggers: List[str]) -> int:
    lowered_values = [value.lower() for value in values]
    count = 0
    for value in lowered_values:
        if any(trigger in value for trigger in triggers):
            count += 1
    return count


def compute_priority(scores: Dict[str, int], reflection: Dict[str, int]) -> Dict[str, Any]:
    base = (
        scores["leverage"] * 4
        + scores["urgency"] * 3
        + scores["dependencyValue"] * 3
        + scores["autonomyImpact"] * 4
        - scores["implementationEffort"] * 2
    )
    reflection_bonus = (
        reflection["repeatedLimitations"] * 2
        + reflection["repeatedUserFriction"] * 3
        + reflection["repeatedManualSteps"] * 2
        + reflection["repeatedEscalationCauses"] * 3
    )
    priority_score = base + reflection_bonus
    relative_priority = "highest" if priority_score >= 45 else "high" if priority_score >= 33 else "medium"
    return {"priorityScore": priority_score, "relativePriority": relative_priority}


def build_improvement_draft(
    capability: str,
    message: str,
    reflection: Dict[str, int],
    scores: Dict[str, int],
) -> Dict[str, Any]:
    normalized = compact_text(message, 160)
    recurring = reflection["total"] >= 3
    if capability == "interface-control":
        return {
            "capability": capability,
            "missingCapability": "direct interface control",
            "whyItMatters": "Interface execution still depends on Alec relaying actions by hand.",
            "whatItUnlocks": "ARI can operate the hub directly instead of stopping at instructions.",
            "smallestSlice": "Ship a safe interface-control bridge for click, scroll, and element targeting inside ACE.",
            "nextBestAction": "Queue the interface-control bridge now and make it the next builder slice.",
            "approvalRequired": True,
            "approvalTitle": "Queue interface-control bridge",
            "approvalBody": "Missing capability: direct interface control. Approve and ARI will queue the bridge as the next implementation slice.",
            "taskTitle": "Implement interface-control bridge for ACE",
            "taskNotes": f'Capability gap detected from request: "{normalized}". Build the safe interface-control bridge now so ARI can act on the hub directly instead of routing this class of work through Alec.',
            "suggestionTitle": "Make interface control the next ARI upgrade",
            "suggestionBody": "This limitation is recurring and is now a real autonomy bottleneck. ARI is still blocked from direct interface execution. The next best move is to ship the interface-control bridge immediately."
            if recurring
            else "ARI is still blocked from direct interface execution. The next best move is to ship the interface-control bridge immediately.",
            "reply": "Missing capability: direct interface control. Why it matters: interface execution still depends on handoff. What it unlocks: ARI can act on the hub directly. Smallest slice: ship the safe interface-control bridge now.",
        }
    if capability == "artifact-generation":
        return {
            "capability": capability,
            "missingCapability": "direct artifact generation pipeline",
            "whyItMatters": "ARI can prepare content but still cannot finish the requested artifact directly.",
            "whatItUnlocks": "ARI can turn prepared content into real exported outputs without a second tool hop.",
            "smallestSlice": "Add one direct generation path for the requested artifact family with a saved output contract.",
            "nextBestAction": "Queue the artifact-generation pipeline now so prepared content can become executable output.",
            "approvalRequired": True,
            "approvalTitle": "Queue artifact-generation pipeline",
            "approvalBody": "Missing capability: direct artifact-generation pipeline. Approve and ARI will queue the smallest generation slice now.",
            "taskTitle": "Add artifact-generation pipeline",
            "taskNotes": f'Capability gap detected from request: "{normalized}". Build the smallest direct generation/export path now so ARI can produce the requested artifact directly instead of stopping at preparation.',
            "suggestionTitle": "Add the missing artifact pipeline",
            "suggestionBody": "This request pattern is repeating, so the missing generation path is now costing time. ARI should stop ending artifact requests at planning. The next implementation slice is the direct generation path."
            if reflection["repeatedUserFriction"] >= 2
            else "ARI should stop ending artifact requests at planning. The next implementation slice is the direct generation path.",
            "reply": "Missing capability: direct artifact generation. Why it matters: ARI can prepare content but not finish the output. What it unlocks: direct exported artifacts. Smallest slice: add the requested generation path now.",
        }
    return {
        "capability": capability,
        "missingCapability": "notification delivery channel",
        "whyItMatters": "Important approvals and alerts still depend on Alec opening the hub at the right moment.",
        "whatItUnlocks": "ARI can surface urgent state outside the browser tab and tighten the approval loop.",
        "smallestSlice": "Add one reliable browser-or-phone notification channel for approvals and high-signal alerts.",
        "nextBestAction": "Queue the notification delivery slice now so important signals can leave the hub cleanly.",
        "approvalRequired": True,
        "approvalTitle": "Queue notification delivery channel",
        "approvalBody": "Missing capability: notification delivery channel. Approve and ARI will queue the smallest delivery slice now.",
        "taskTitle": "Add notification delivery channel",
        "taskNotes": f'Capability gap detected from request: "{normalized}". Build browser or phone notification delivery now so ARI can push approvals and important alerts beyond the hub.',
        "suggestionTitle": "Push signals beyond the hub",
        "suggestionBody": "This is repeatedly falling back to hub-only visibility, which is now a coordination drag. ARI identified notification delivery as the next clean way to reduce missed approvals and alerts."
        if reflection["repeatedManualSteps"] >= 2
        else "ARI identified notification delivery as the next clean way to reduce missed approvals and alerts.",
        "reply": "Missing capability: notification delivery. Why it matters: approvals and alerts stay trapped in the hub. What it unlocks: timely signals outside the browser. Smallest slice: add the first delivery channel now.",
    }


def detect_capability_gaps(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    message = (payload.get("message") or "").strip()
    if not message:
        return []
    recent_messages = [item for item in payload.get("recentMessages", []) if isinstance(item, str)]
    task_notes = [item for item in payload.get("taskNotes", []) if isinstance(item, str)]
    escalation_texts = [item for item in payload.get("escalationTexts", []) if isinstance(item, str)]
    approval_counts = payload.get("approvalCounts", {}) if isinstance(payload.get("approvalCounts", {}), dict) else {}
    lowered_message = message.lower()
    drafts: List[Dict[str, Any]] = []

    for rule in IMPROVEMENT_RULES:
        if not any(trigger in lowered_message for trigger in rule["triggers"]):
            continue
        reflection = {
            "repeatedLimitations": clamp_count(int(approval_counts.get(rule["capability"], 0))),
            "repeatedUserFriction": clamp_count(count_trigger_matches(recent_messages, rule["triggers"])),
            "repeatedManualSteps": clamp_count(count_trigger_matches(task_notes, rule["triggers"])),
            "repeatedEscalationCauses": clamp_count(count_trigger_matches(escalation_texts, rule["triggers"])),
        }
        reflection["total"] = (
            reflection["repeatedLimitations"]
            + reflection["repeatedUserFriction"]
            + reflection["repeatedManualSteps"]
            + reflection["repeatedEscalationCauses"]
        )
        scored = compute_priority(rule["baseScores"], reflection)
        proposal = build_improvement_draft(rule["capability"], message, reflection, rule["baseScores"])
        drafts.append(
            {
                **proposal,
                "leverage": rule["baseScores"]["leverage"],
                "urgency": rule["baseScores"]["urgency"],
                "dependencyValue": rule["baseScores"]["dependencyValue"],
                "autonomyImpact": rule["baseScores"]["autonomyImpact"],
                "implementationEffort": rule["baseScores"]["implementationEffort"],
                "priorityScore": scored["priorityScore"],
                "relativePriority": scored["relativePriority"],
                "reflection": reflection,
                "dedupeKey": f'capability-gap:{rule["capability"]}',
                "keywords": rule["keywords"],
            }
        )
    return sorted(drafts, key=lambda item: (-int(item["priorityScore"]), int(item["implementationEffort"])))


def build_project_draft(payload: Dict[str, Any], db_path: Path = DB_PATH) -> Dict[str, Any]:
    goal = (payload.get("goal") or "").strip()
    source = payload.get("source") or "manual"
    normalized_goal = " ".join(goal.split())
    title = compact_text(normalized_goal, 68) or "Project"
    top_improvement = get_top_improvement_focus(db_path=db_path)
    if top_improvement:
        step_two_title = f'Execute the blocking slice for {top_improvement["missingCapability"]}'
        step_two_criteria = f'{top_improvement["missingCapability"]} has been dispatched and produces execution evidence.'
    else:
        step_two_title = f"Execute the core implementation slice for {title}"
        step_two_criteria = f"The core implementation slice for {title} is executed and produces evidence."
    return {
        "title": title,
        "goal": normalized_goal,
        "completionCriteria": f"Done means {normalized_goal} is implemented, verified, and folded back into ARI state.",
        "source": source,
        "milestones": [
            {
                "title": "Establish the execution path",
                "completionCriteria": "The near-term path and first unblocker are defined.",
                "steps": [
                    {
                        "title": f"Map the smallest execution path for {title}",
                        "completionCriteria": "The project has a concrete, dependency-aware path.",
                        "dependsOnIndexes": [],
                    }
                ],
            },
            {
                "title": "Execute the core slice",
                "completionCriteria": "The main implementation slice has been executed with evidence.",
                "steps": [
                    {
                        "title": step_two_title,
                        "completionCriteria": step_two_criteria,
                        "dependsOnIndexes": [0],
                        "linkedImprovementId": top_improvement["id"] if top_improvement else None,
                    }
                ],
            },
            {
                "title": "Verify and close the loop",
                "completionCriteria": "Outcome is verified and the project state reflects the result.",
                "steps": [
                    {
                        "title": f"Verify the execution path for {title}",
                        "completionCriteria": "Verification evidence exists for the project goal.",
                        "dependsOnIndexes": [1],
                    },
                    {
                        "title": f"Fold the verified result back into ARI state for {title}",
                        "completionCriteria": "ARI memory and hub state reflect the completed project outcome.",
                        "dependsOnIndexes": [2],
                    },
                ],
            },
        ],
    }


def score_task(task: Dict[str, Any], priorities: List[Dict[str, Any]], recent_decisions: List[Dict[str, Any]]) -> int:
    lowered = f'{task["title"]} {task["notes"]}'.lower()
    score = 50
    if priorities:
        words = [word for word in priorities[0]["content"].lower().split() if len(word) > 3]
        score += len([word for word in words if word in lowered]) * 10
    if recent_decisions:
        words = [word for word in recent_decisions[0]["body"].lower().split() if len(word) > 4]
        score += len([word for word in words if word in lowered]) * 4
    return score


def list_pending_escalations(db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    rows = list_coordination("orchestration_record", limit=200, db_path=db_path)
    pending = [row for row in rows if row["escalation_required"] == 1 and not (row["alec_decision"] or "").strip()]
    pending.sort(key=lambda row: row["created_at"], reverse=True)
    return [
        {
            "id": row["id"],
            "conciseSummary": row["concise_summary"],
            "escalationPacket": parse_json_object(row["escalation_packet_json"], {}),
            "createdAt": row["created_at"],
        }
        for row in pending
    ]


def derive_awareness(payload: Dict[str, Any], db_path: Path = DB_PATH) -> Dict[str, Any]:
    pending_approvals = payload.get("pendingApprovals", []) if isinstance(payload.get("pendingApprovals", []), list) else []
    recent_intent = [item for item in payload.get("recentIntent", []) if isinstance(item, str)][:3]
    recent_decisions = payload.get("recentDecisions", []) if isinstance(payload.get("recentDecisions", []), list) else []
    priorities = list_memories(["priority"], limit=4, db_path=db_path)
    active_projects = list_memories(["active_project"], limit=4, db_path=db_path)
    current_tasks = [task for task in list_tasks(limit=20, db_path=db_path) if task["status"] == "open"]
    top_improvement = get_top_improvement_focus(db_path=db_path)
    project_focus = sync_project_focus(db_path=db_path)
    pending_escalations = list_pending_escalations(db_path=db_path)
    current_focus: List[Dict[str, Any]] = []

    if pending_escalations:
        escalation = pending_escalations[0]
        packet = escalation.get("escalationPacket", {})
        current_focus.append(
            {
                "id": f'focus-orchestration-{escalation["id"]}',
                "kind": "orchestration",
                "title": "Alec decision is blocking the builder loop",
                "reason": packet.get("whyEscalationIsNeeded")
                or escalation.get("conciseSummary")
                or "ARI is paused until Alec resolves the escalation packet.",
                "nextAction": packet.get("exactQuestionForAlec") or "Record Alec's decision so ARI can continue orchestration.",
                "score": 100,
                "blocking": True,
                "sourceId": escalation["id"],
            }
        )

    if pending_approvals:
        approval = pending_approvals[0]
        current_focus.append(
            {
                "id": f'focus-approval-{approval["id"]}',
                "kind": "approval",
                "title": approval["title"],
                "reason": compact_text(approval["body"], 120),
                "nextAction": "Approve or deny the request to clear the blocker.",
                "score": 92,
                "blocking": True,
                "sourceId": approval["id"],
            }
        )

    if project_focus and project_focus.get("nextStep"):
        current_focus.append(
            {
                "id": f'focus-project-{project_focus["project"]["id"]}',
                "kind": "project",
                "title": project_focus["project"]["title"],
                "reason": (
                    f'Current milestone: {project_focus["currentMilestone"]["title"]}'
                    if project_focus.get("currentMilestone")
                    else "Project execution path is active."
                ),
                "nextAction": project_focus["nextStep"]["title"],
                "score": 78 if project_focus.get("majorBlocker") else 84,
                "blocking": bool(project_focus.get("majorBlocker")),
                "sourceId": project_focus["project"]["id"],
            }
        )

    if top_improvement and top_improvement["status"] != "verified":
        status_boost = {"queued": 10, "approved": 8, "dispatched": 7, "completed": 5}.get(top_improvement["status"], 0)
        current_focus.append(
            {
                "id": f'focus-improvement-{top_improvement["id"]}',
                "kind": "improvement",
                "title": top_improvement["missingCapability"],
                "reason": f'{top_improvement["whyItMatters"]} Unlocks: {top_improvement["whatItUnlocks"]}',
                "nextAction": top_improvement["nextBestAction"],
                "score": 48 + int(top_improvement["priorityScore"]) + status_boost + int(top_improvement["reflection"]["total"]) * 2,
                "blocking": False,
                "sourceId": top_improvement["id"],
            }
        )

    if current_tasks:
        lead_task = sorted(current_tasks, key=lambda task: -score_task(task, priorities, recent_decisions))[0]
        current_focus.append(
            {
                "id": f'focus-task-{lead_task["id"]}',
                "kind": "task",
                "title": lead_task["title"],
                "reason": f'This task best supports the current priority: {priorities[0]["content"]}'
                if priorities
                else "This is the strongest open task in ARI's current working state.",
                "nextAction": f'Advance "{lead_task["title"]}" before adding more work.',
                "score": score_task(lead_task, priorities, recent_decisions),
                "blocking": False,
                "sourceId": lead_task["id"],
            }
        )

    if recent_intent and not any(item["kind"] in {"task", "approval", "orchestration"} for item in current_focus):
        current_focus.append(
            {
                "id": "focus-intent-latest",
                "kind": "decision",
                "title": "Recent operator intent is still active",
                "reason": recent_intent[0],
                "nextAction": "Keep the next action aligned with Alec's most recent directive.",
                "score": 56,
                "blocking": False,
            }
        )

    current_focus = sorted(current_focus, key=lambda item: -int(item["score"]))[:2]
    tracking: List[str] = []
    if priorities:
        tracking.append(f'Priority in memory: {compact_text(priorities[0]["content"], 84)}')
    if active_projects:
        tracking.append(f'Active project: {compact_text(active_projects[0]["content"], 84)}')
    if project_focus:
        tracking.append(
            f'Project blocker: {project_focus["majorBlocker"]}'
            if project_focus.get("majorBlocker")
            else f'Project next step: {project_focus["nextStep"]["title"] if project_focus.get("nextStep") else project_focus["progressSummary"]}'
        )
    if current_tasks:
        tracking.append(f'{len(current_tasks)} open task(s). Lead item: {current_tasks[0]["title"]}')
    if pending_approvals:
        tracking.append(f"{len(pending_approvals)} approval request(s) are waiting.")
    if top_improvement:
        tracking.append(f'Improvement focus: {top_improvement["missingCapability"]} is {top_improvement["status"]}.')
    if pending_escalations:
        packet = pending_escalations[0].get("escalationPacket", {})
        tracking.append(packet.get("whyEscalationIsNeeded") or "Builder orchestration is paused for Alec.")
    if recent_intent:
        tracking.append(f"Recent intent: {recent_intent[0]}")
    tracking = tracking[:5]

    if current_focus and current_focus[0]["blocking"]:
        mode = "blocked"
        summary = f'{current_focus[0]["title"]}. {current_focus[0]["nextAction"]}'
    elif current_focus:
        mode = "active"
        summary = (
            f'Current focus: {current_focus[0]["title"]}. Secondary focus: {current_focus[1]["title"]}.'
            if len(current_focus) > 1
            else f'Current focus: {current_focus[0]["title"]}. {current_focus[0]["nextAction"]}'
        )
    elif tracking:
        mode = "steady"
        summary = tracking[0]
    else:
        mode = "steady"
        summary = "ARI is in quiet monitoring mode."

    snapshot = {
        "id": payload.get("id") or f"awareness-{int(parse_iso_sort(now_iso()))}",
        "mode": mode,
        "summary": summary,
        "currentFocus": current_focus,
        "tracking": tracking,
        "recentIntent": recent_intent,
        "signature": json.dumps(
            {
                "mode": mode,
                "focus": [{"id": item["id"], "score": item["score"], "blocking": item["blocking"]} for item in current_focus],
                "tracking": tracking,
                "recentIntent": recent_intent,
            },
            sort_keys=True,
        ),
        "updatedAt": now_iso(),
    }
    return snapshot
