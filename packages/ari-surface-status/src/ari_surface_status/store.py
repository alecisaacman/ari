from __future__ import annotations

import os
from pathlib import Path

from ari_surface_status.models import SurfaceStatus

DEFAULT_SURFACE_STATUS_DIR = "data/surface/status"


class SurfaceStatusStore:
    def __init__(self, root_dir: Path | None = None) -> None:
        configured_root = root_dir or Path(
            os.environ.get("ARI_SURFACE_STATUS_DIR", DEFAULT_SURFACE_STATUS_DIR)
        )
        self.root_dir = configured_root.expanduser()
        self.current_path = self.root_dir / "current.json"
        self.history_dir = self.root_dir / "history"

    def write(self, status: SurfaceStatus) -> Path:
        self.history_dir.mkdir(parents=True, exist_ok=True)
        payload = status.model_dump_json(indent=2)
        history_path = self.history_dir / f"{status.status_id}.json"
        history_path.write_text(payload + "\n", encoding="utf-8")
        self.current_path.parent.mkdir(parents=True, exist_ok=True)
        self.current_path.write_text(payload + "\n", encoding="utf-8")
        return history_path

    def load_current(self) -> SurfaceStatus | None:
        if not self.current_path.exists():
            return None
        return SurfaceStatus.model_validate_json(self.current_path.read_text(encoding="utf-8"))
