from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .surface_status import SurfaceStatus, SurfaceStatusStore, read_current_surface_status

DEFAULT_TUX_ASSET_ROOT = Path("/Users/alecisaacman/ARI (codex)/pet-runs/tux")
TUX_ASSET_ROOT_ENV = "ARI_TUX_ASSET_ROOT"
TUX_FRAME_WIDTH = 192
TUX_FRAME_HEIGHT = 208


class TuxStatusPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_present: bool
    current_status_path: str
    ari_state: str | None
    tux_animation_state: str
    summary: str
    source: str | None
    event_id: str | None
    updated_at: str | None
    asset_root: str
    sprite_path: str
    frame_directory: str
    frames_manifest_path: str
    frame_width: int
    frame_height: int
    assets_present: bool
    has_frame_directory: bool
    has_sprite: bool
    has_frames_manifest: bool
    missing_assets: list[str]

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class TuxStatusAdapter:
    def __init__(
        self,
        *,
        status_dir: Path | None = None,
        asset_root: Path | None = None,
    ) -> None:
        self.store = SurfaceStatusStore(status_dir)
        self.asset_root = resolve_tux_asset_root(asset_root)

    def preview(self) -> TuxStatusPreview:
        return build_tux_status_preview(
            status_dir=self.store.root_dir,
            asset_root=self.asset_root,
        )


def build_tux_status_preview(
    *,
    status_dir: Path | None = None,
    asset_root: Path | None = None,
) -> TuxStatusPreview:
    store = SurfaceStatusStore(status_dir)
    status = read_current_surface_status(root_dir=store.root_dir)
    tux_state = status.tux_state if status is not None else "idle"
    resolved_asset_root = resolve_tux_asset_root(asset_root)
    sprite_path = _resolve_sprite_path(resolved_asset_root)
    frame_directory = resolved_asset_root / "frames" / tux_state
    frames_manifest_path = resolved_asset_root / "frames" / "frames-manifest.json"

    has_frame_directory = frame_directory.is_dir()
    has_sprite = sprite_path.exists()
    has_frames_manifest = frames_manifest_path.is_file()
    missing_assets = _missing_assets(
        has_frame_directory=has_frame_directory,
        has_sprite=has_sprite,
        has_frames_manifest=has_frames_manifest,
        tux_state=tux_state,
    )

    return TuxStatusPreview(
        status_present=status is not None,
        current_status_path=str(store.current_path),
        ari_state=status.state.value if status is not None else None,
        tux_animation_state=tux_state,
        summary=_summary(status),
        source=status.source if status is not None else None,
        event_id=status.event_id if status is not None else None,
        updated_at=(
            status.updated_at.isoformat().replace("+00:00", "Z")
            if status is not None
            else None
        ),
        asset_root=str(resolved_asset_root),
        sprite_path=str(sprite_path),
        frame_directory=str(frame_directory),
        frames_manifest_path=str(frames_manifest_path),
        frame_width=TUX_FRAME_WIDTH,
        frame_height=TUX_FRAME_HEIGHT,
        assets_present=not missing_assets,
        has_frame_directory=has_frame_directory,
        has_sprite=has_sprite,
        has_frames_manifest=has_frames_manifest,
        missing_assets=missing_assets,
    )


def resolve_tux_asset_root(asset_root: Path | None = None) -> Path:
    if asset_root is not None:
        return asset_root.expanduser()
    configured_root = os.environ.get(TUX_ASSET_ROOT_ENV)
    if configured_root:
        return Path(configured_root).expanduser()
    return DEFAULT_TUX_ASSET_ROOT


def _resolve_sprite_path(asset_root: Path) -> Path:
    png_path = asset_root / "final" / "spritesheet.png"
    if png_path.exists():
        return png_path
    webp_path = asset_root / "final" / "spritesheet.webp"
    if webp_path.exists():
        return webp_path
    return png_path


def _summary(status: SurfaceStatus | None) -> str:
    if status is None:
        return "No current ARI surface status found."
    return status.summary


def _missing_assets(
    *,
    has_frame_directory: bool,
    has_sprite: bool,
    has_frames_manifest: bool,
    tux_state: str,
) -> list[str]:
    missing_assets: list[str] = []
    if not has_frame_directory:
        missing_assets.append(f"frames/{tux_state}/")
    if not has_sprite:
        missing_assets.append("final/spritesheet.png or final/spritesheet.webp")
    if not has_frames_manifest:
        missing_assets.append("frames/frames-manifest.json")
    return missing_assets
