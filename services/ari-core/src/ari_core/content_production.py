"""Moving content through the content process, with production started for real.

Every surface (the hub, the API, ARI's tools) moves content through here, so the
same thing happens however Alec asks: when an item enters production, ARI's studio
(tools/ari-studio) starts making its video in the background, in Alec's cloned voice,
and attaches it to the item when it's done, for Alec to watch on the Content page.
Marking it ready to post stays Alec's call, and needs the video. Stepping back into
production from ready keeps the video; Alec asks for a remake by starting over from the
script.

The studio runs in its own environment (~/ARI/media/venv); without it, production is
a stage Alec marks by hand.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from ari_core.core.env import ari_home
from ari_core.core.paths import DB_PATH
from ari_core.modules.self_documentation.library import ContentItem, get_content_item, set_status

Spawn = Callable[[Sequence[str]], None]


def studio_command(item: ContentItem) -> list[str] | None:
    """The command that makes an item's video, or None if the studio isn't installed."""
    python = ari_home() / "media" / "venv" / "bin" / "python"
    studio = ari_home() / "runtime" / "current" / "tools" / "ari-studio" / "studio.py"
    if item.day_number is None or not python.exists() or not studio.exists() or not _narration_available():
        return None
    return [str(python), str(studio), "produce", "--day", str(item.day_number), "--attach"]


def move(item_id: str, status: str, *, db_path: Path = DB_PATH, spawn: Spawn | None = None) -> tuple[ContentItem | None, bool]:
    """Move an item a stage. Returns it, and whether the studio started making its video."""
    before = get_content_item(item_id, db_path=db_path)
    item = set_status(item_id, status, db_path=db_path)
    if item is None or before is None or not (before.status == "script" and status == "production"):
        return item, False
    command = studio_command(item)
    if command is None:
        return item, False
    (spawn or _spawn_detached)(command)
    return item, True


def _narration_available() -> bool:
    """Narration needs Replicate connected, or a Mac told it can run the model itself.

    This Mac's 8 GB can't, so without either, production stays a stage marked by hand.
    """
    return bool(os.environ.get("REPLICATE_API_TOKEN")) or os.environ.get("ARI_STUDIO_VOICE") == "local"


def _spawn_detached(command: Sequence[str]) -> None:
    log = ari_home() / "media" / "studio.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as out:
        subprocess.Popen(list(command), stdout=out, stderr=out, start_new_session=True, env={**os.environ})
