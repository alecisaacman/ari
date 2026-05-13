from __future__ import annotations

from ari_core.surface_status import SurfaceState, SurfaceStatus, build_surface_status


def surface_status_from_telegram_event(event: object) -> SurfaceStatus:
    authorized = bool(getattr(event, "authorized", False))
    event_id = str(getattr(event, "event_id", "") or "")
    raw_text = str(getattr(event, "raw_text", "") or "")
    assigned_role = _enum_value(getattr(event, "assigned_role", ""))
    normalized_intent = _enum_value(getattr(event, "normalized_intent", ""))
    requires_approval = bool(getattr(event, "requires_approval", False))
    status = _enum_value(getattr(event, "status", ""))
    task_id = _pending_task_id(getattr(event, "pending_codex_task", None))

    metadata = {
        "surface": "telegram",
        "assigned_role": assigned_role,
        "normalized_intent": normalized_intent,
    }

    if not authorized or status == "rejected":
        return build_surface_status(
            state=SurfaceState.BLOCKED,
            summary="ARI blocked an unauthorized Telegram update.",
            source="telegram",
            event_id=event_id or None,
            metadata=metadata,
        )

    if assigned_role == "CTO_CODEX" and requires_approval:
        return build_surface_status(
            state=SurfaceState.WAITING_FOR_APPROVAL,
            summary=_truncate(raw_text) or "A Telegram Codex task requires approval.",
            source="telegram",
            event_id=event_id or None,
            task_id=task_id,
            metadata={**metadata, "requires_approval": True},
        )

    if assigned_role == "CPO" and normalized_intent in {
        "competitor_intel",
        "product_inspiration",
    }:
        return build_surface_status(
            state=SurfaceState.WORKING,
            summary=_truncate(raw_text) or "ARI captured a product or competitor signal.",
            source="telegram",
            event_id=event_id or None,
            metadata=metadata,
        )

    if assigned_role == "MEMORY" or normalized_intent == "memory_capture":
        return build_surface_status(
            state=SurfaceState.SUCCESS,
            summary=_truncate(raw_text) or "ARI captured a memory update.",
            source="telegram",
            event_id=event_id or None,
            metadata=metadata,
        )

    return build_surface_status(
        state=SurfaceState.SUCCESS,
        summary=_truncate(raw_text) or "ARI processed a Telegram update.",
        source="telegram",
        event_id=event_id or None,
        metadata=metadata,
    )


def career_command_status(
    *,
    command: str,
    ok: bool,
    message: str,
    event_id: str | None = None,
) -> SurfaceStatus:
    command_name = command.strip().lower()
    if not ok:
        return build_surface_status(
            state=SurfaceState.ERROR,
            summary=_truncate(message) or "Career Command returned an error.",
            source="career_command",
            event_id=event_id,
            metadata={"surface": "telegram", "command": command_name},
        )

    if command_name in {
        "status",
        "tracker",
        "pending",
        "latest",
        "dashboard",
        "help",
        "scout_preview",
        "save",
        "draft",
        "approve",
        "reject",
    }:
        state = SurfaceState.SUCCESS
    else:
        state = SurfaceState.WAITING_FOR_APPROVAL

    return build_surface_status(
        state=state,
        summary=_truncate(message) or "Career Command completed.",
        source="career_command",
        event_id=event_id,
        metadata={"surface": "telegram", "command": command_name},
    )


def _enum_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "")


def _pending_task_id(value: object) -> str | None:
    task_id = getattr(value, "task_id", None)
    if task_id is None:
        task_id = getattr(value, "codex_task_id", None)
    if task_id is None:
        return None
    normalized = str(task_id).strip()
    return normalized or None


def _truncate(value: str, *, limit: int = 220) -> str:
    text = " ".join(value.strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."
