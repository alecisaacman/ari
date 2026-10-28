from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from ari_core.core.env import ari_home


@dataclass(frozen=True, slots=True)
class ImessageSettings:
    """Where the self-thread is and how ARI reaches Alec there.

    Identifiers are personal, so they come only from the local environment and
    are never written into the repository.
    """

    self_identifiers: tuple[str, ...]
    reply_to: str | None
    dump_path: Path
    state_dir: Path
    stale_after: timedelta = timedelta(minutes=2)
    quiet_hours: tuple[int, int] | None = (22, 7)
    # When ARI sends its morning and night reviews, local time; None turns one off.
    review_times: dict[str, tuple[int, int] | None] = field(
        default_factory=lambda: {"morning": (8, 0), "night": (21, 0)}
    )

    @classmethod
    def from_env(cls) -> ImessageSettings:
        reply_to = os.environ.get("ARI_IMESSAGE_TO", "").strip() or None
        raw = os.environ.get("ARI_IMESSAGE_SELF_IDENTIFIERS", "") or (reply_to or "")
        identifiers = tuple(item.strip() for item in raw.split(",") if item.strip())
        state_dir = ari_home() / "imessage"
        dump_path = Path(
            os.environ.get("ARI_IMESSAGE_DUMP_PATH", str(state_dir / "self-thread.tsv"))
        ).expanduser()
        return cls(
            self_identifiers=identifiers,
            reply_to=reply_to or (identifiers[0] if identifiers else None),
            dump_path=dump_path,
            state_dir=state_dir,
            quiet_hours=_quiet_hours(os.environ.get("ARI_QUIET_HOURS", "22-7")),
            review_times={
                "morning": _clock_time(os.environ.get("ARI_REVIEW_MORNING", "08:00")),
                "night": _clock_time(os.environ.get("ARI_REVIEW_NIGHT", "21:00")),
            },
        )


def _clock_time(raw: str) -> tuple[int, int] | None:
    """`08:00` is 8 AM local time; `off` turns that review off."""
    if raw.strip().lower() in {"", "off", "none"}:
        return None
    hour, _, minute = raw.strip().partition(":")
    return int(hour), int(minute or 0)


def _quiet_hours(raw: str) -> tuple[int, int] | None:
    """`22-7` means 22:00 to 07:00 local time; `off` disables quiet hours."""
    if raw.strip().lower() in {"", "off", "none"}:
        return None
    start, _, end = raw.partition("-")
    return int(start), int(end)
