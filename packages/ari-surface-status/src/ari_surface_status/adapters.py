from __future__ import annotations

from ari_surface_status.models import SurfaceSeverity, SurfaceState, SurfaceStatus


def surface_status_from_telegram_event(event: object) -> SurfaceStatus:
    authorized = bool(getattr(event, "authorized", False))
    event_id = str(getattr(event, "event_id", "") or "")
    raw_text = str(getattr(event, "raw_text", "") or "")
    assigned_role = _enum_value(getattr(event, "assigned_role", ""))
    normalized_intent = _enum_value(getattr(event, "normalized_intent", ""))
    requires_approval = bool(getattr(event, "requires_approval", False))
    status = _enum_value(getattr(event, "status", ""))

    if not authorized or status == "rejected":
        return SurfaceStatus(
            state=SurfaceState.BLOCKED,
            severity=SurfaceSeverity.WARNING,
            title="Telegram sender rejected",
            message="ARI blocked an unauthorized Telegram update.",
            source="telegram",
            surface="telegram",
            event_id=event_id or None,
            metadata={
                "assigned_role": assigned_role,
                "normalized_intent": normalized_intent,
            },
        )

    if assigned_role == "CTO_CODEX" and requires_approval:
        return SurfaceStatus(
            state=SurfaceState.WAITING_FOR_APPROVAL,
            severity=SurfaceSeverity.WARNING,
            title="Codex task waiting for approval",
            message=_truncate(raw_text) or "A Telegram Codex task requires approval.",
            source="telegram",
            surface="telegram",
            event_id=event_id or None,
            metadata={
                "assigned_role": assigned_role,
                "normalized_intent": normalized_intent,
                "requires_approval": True,
            },
        )

    if assigned_role == "CPO" and normalized_intent in {
        "competitor_intel",
        "product_inspiration",
    }:
        return SurfaceStatus(
            state=SurfaceState.WORKING,
            severity=SurfaceSeverity.INFO,
            title="Product signal captured",
            message=_truncate(raw_text) or "ARI captured a product or competitor signal.",
            source="telegram",
            surface="telegram",
            event_id=event_id or None,
            metadata={"assigned_role": assigned_role, "normalized_intent": normalized_intent},
        )

    if assigned_role == "MEMORY" or normalized_intent == "memory_capture":
        return SurfaceStatus(
            state=SurfaceState.SUCCESS,
            severity=SurfaceSeverity.INFO,
            title="Memory captured",
            message=_truncate(raw_text) or "ARI captured a memory update.",
            source="telegram",
            surface="telegram",
            event_id=event_id or None,
            metadata={"assigned_role": assigned_role, "normalized_intent": normalized_intent},
        )

    return SurfaceStatus(
        state=SurfaceState.SUCCESS,
        severity=SurfaceSeverity.INFO,
        title="Telegram update processed",
        message=_truncate(raw_text) or "ARI processed a Telegram update.",
        source="telegram",
        surface="telegram",
        event_id=event_id or None,
        metadata={"assigned_role": assigned_role, "normalized_intent": normalized_intent},
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
        return SurfaceStatus(
            state=SurfaceState.ERROR,
            severity=SurfaceSeverity.ERROR,
            title="Career Command failed",
            message=_truncate(message) or "Career Command returned an error.",
            source="career_command",
            surface="telegram",
            event_id=event_id,
            command=command_name,
        )

    if command_name in {"status", "tracker", "pending", "latest", "dashboard", "help"}:
        state = SurfaceState.SUCCESS
        title = "Career Command read completed"
    elif command_name == "scout_preview":
        state = SurfaceState.SUCCESS
        title = "Career scout preview completed"
    elif command_name in {"save", "draft", "approve", "reject"}:
        state = SurfaceState.SUCCESS
        title = "Career Command operation completed"
    else:
        state = SurfaceState.WAITING_FOR_APPROVAL
        title = "Career Command needs user choice"

    return SurfaceStatus(
        state=state,
        severity=SurfaceSeverity.INFO,
        title=title,
        message=_truncate(message) or "Career Command completed.",
        source="career_command",
        surface="telegram",
        event_id=event_id,
        command=command_name,
    )


def _enum_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "")


def _truncate(value: str, *, limit: int = 220) -> str:
    text = " ".join(value.strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."
