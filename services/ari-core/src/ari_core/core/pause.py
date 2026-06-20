import json
from datetime import datetime, timezone
from typing import Any, Dict

from .paths import ARI_STATE_DIR

PAUSED_MARKER_PATH = ARI_STATE_DIR / ".paused"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_paused() -> bool:
    return PAUSED_MARKER_PATH.exists()


def get_pause_state() -> Dict[str, Any]:
    if not PAUSED_MARKER_PATH.exists():
        return {"paused": False, "reason": None, "pausedAt": None}
    try:
        data = json.loads(PAUSED_MARKER_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {}
    return {
        "paused": True,
        "reason": data.get("reason"),
        "pausedAt": data.get("pausedAt"),
    }


def pause(reason: str = "") -> Dict[str, Any]:
    PAUSED_MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"pausedAt": _now_iso(), "reason": reason}
    PAUSED_MARKER_PATH.write_text(json.dumps(payload), encoding="utf-8")
    return get_pause_state()


def resume() -> Dict[str, Any]:
    PAUSED_MARKER_PATH.unlink(missing_ok=True)
    return get_pause_state()


def ensure_not_paused() -> None:
    state = get_pause_state()
    if state["paused"]:
        reason = state.get("reason") or "no reason given"
        raise ValueError(
            f"Execution is paused ({reason}). Resume with `ari resume` before retrying."
        )


def handle_pause(args) -> int:
    print(json.dumps(pause(getattr(args, "reason", "") or "")))
    return 0


def handle_resume(args) -> int:
    print(json.dumps(resume()))
    return 0


def handle_paused(args) -> int:
    print(json.dumps(get_pause_state()))
    return 0
