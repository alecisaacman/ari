from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path


def ari_home() -> Path:
    return Path(os.environ.get("ARI_HOME", str(Path.home() / "ARI"))).expanduser()


def load_local_env(path: Path) -> None:
    """Read KEY=VALUE lines from Alec's private env file without overriding the environment.

    Secrets and personal identifiers live here (ARI_HOME/ari.env, mode 600), never
    in a plist or the repository.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


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
        )


def _quiet_hours(raw: str) -> tuple[int, int] | None:
    """`22-7` means 22:00 to 07:00 local time; `off` disables quiet hours."""
    if raw.strip().lower() in {"", "off", "none"}:
        return None
    start, _, end = raw.partition("-")
    return int(start), int(end)
