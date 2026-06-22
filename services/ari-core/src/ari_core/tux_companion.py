from __future__ import annotations

import json
import logging
import os
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .surface_status import SurfaceStatusStore
from .tux_status import (
    TuxStatusPreview,
    build_tux_status_preview,
    resolve_tux_asset_root,
)

CLICK_TARGET_ENV = "ARI_TUX_CLICK_TARGET"
DEFAULT_POLL_INTERVAL_SECONDS = 1.5
DEFAULT_FRAME_INTERVAL_MS = 140
TRANSPARENT_COLOR = "#ff00ff"

LOGGER = logging.getLogger(__name__)


class StatusReader(Protocol):
    def __call__(self, *, status_dir: Path | None, asset_root: Path) -> TuxStatusPreview: ...


@dataclass(frozen=True)
class TuxCompanionConfig:
    asset_root: Path
    status_dir: Path | None
    poll_interval: float
    click_target: str | None
    show_bubble: bool
    debug: bool

    @property
    def resolved_status_dir(self) -> Path:
        return SurfaceStatusStore(self.status_dir).root_dir


@dataclass(frozen=True)
class TuxAnimationFrames:
    state: str
    directory: Path
    frame_paths: tuple[Path, ...]


@dataclass(frozen=True)
class TuxCompanionSnapshot:
    preview: TuxStatusPreview
    frames: TuxAnimationFrames
    bubble_text: str

    def to_dict(self) -> dict[str, object]:
        payload = self.preview.to_dict()
        payload["bubble_text"] = self.bubble_text
        payload["selected_frames"] = [str(frame_path) for frame_path in self.frames.frame_paths]
        payload["selected_frame_count"] = len(self.frames.frame_paths)
        return payload


class TuxAssetError(RuntimeError):
    def __init__(self, message: str, *, missing_assets: list[str]) -> None:
        super().__init__(message)
        self.missing_assets = missing_assets


def build_tux_companion_config(
    *,
    asset_root: Path | None = None,
    status_dir: Path | None = None,
    poll_interval: float | None = None,
    click_target: str | None = None,
    no_bubble: bool = False,
    debug: bool = False,
) -> TuxCompanionConfig:
    resolved_click_target = click_target
    if resolved_click_target is None:
        resolved_click_target = os.environ.get(CLICK_TARGET_ENV)
    if resolved_click_target is not None:
        resolved_click_target = resolved_click_target.strip() or None

    resolved_poll_interval = (
        DEFAULT_POLL_INTERVAL_SECONDS if poll_interval is None else poll_interval
    )
    if resolved_poll_interval <= 0:
        raise ValueError("--poll-interval must be greater than 0")

    return TuxCompanionConfig(
        asset_root=resolve_tux_asset_root(asset_root),
        status_dir=status_dir.expanduser() if status_dir is not None else None,
        poll_interval=resolved_poll_interval,
        click_target=resolved_click_target,
        show_bubble=not no_bubble,
        debug=debug,
    )


def discover_animation_frames(asset_root: Path, tux_state: str) -> TuxAnimationFrames:
    frame_directory = asset_root / "frames" / tux_state
    if not frame_directory.is_dir():
        raise TuxAssetError(
            f"Tux animation frame directory is missing: {frame_directory}",
            missing_assets=[f"frames/{tux_state}/"],
        )

    frame_paths = tuple(
        sorted(
            (
                path
                for path in frame_directory.iterdir()
                if path.is_file() and path.suffix.lower() == ".png"
            ),
            key=_frame_sort_key,
        )
    )
    if not frame_paths:
        raise TuxAssetError(
            f"Tux animation frame directory has no PNG frames: {frame_directory}",
            missing_assets=[f"frames/{tux_state}/*.png"],
        )

    return TuxAnimationFrames(
        state=tux_state,
        directory=frame_directory,
        frame_paths=frame_paths,
    )


def build_bubble_text(preview: TuxStatusPreview) -> str:
    ari_state = preview.ari_state or "idle"
    return f"{ari_state} · {preview.tux_animation_state}\n{preview.summary}"


def read_tux_companion_snapshot(
    config: TuxCompanionConfig,
    *,
    status_reader: StatusReader = build_tux_status_preview,
) -> TuxCompanionSnapshot:
    preview = status_reader(status_dir=config.status_dir, asset_root=config.asset_root)
    frames = discover_animation_frames(config.asset_root, preview.tux_animation_state)
    return TuxCompanionSnapshot(
        preview=preview,
        frames=frames,
        bubble_text=build_bubble_text(preview),
    )


def dry_run_tux_companion(config: TuxCompanionConfig) -> int:
    try:
        snapshot = read_tux_companion_snapshot(config)
    except TuxAssetError as exc:
        print(f"Tux companion dry-run failed: {exc}", file=sys.stderr)
        if exc.missing_assets:
            print("Missing assets:", file=sys.stderr)
            for missing_asset in exc.missing_assets:
                print(f"- {missing_asset}", file=sys.stderr)
        return 1

    print(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True))
    return 0


def launch_tux_companion(config: TuxCompanionConfig) -> int:
    _configure_logging(config.debug)
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"Unable to launch Tux companion: tkinter is unavailable: {exc}", file=sys.stderr)
        return 1

    try:
        app = _TuxCompanionTkApp(config=config, tk_module=tk)
    except TuxAssetError as exc:
        print(f"Unable to launch Tux companion: {exc}", file=sys.stderr)
        if exc.missing_assets:
            print("Missing assets:", file=sys.stderr)
            for missing_asset in exc.missing_assets:
                print(f"- {missing_asset}", file=sys.stderr)
        return 1
    except tk.TclError as exc:
        print(f"Unable to launch Tux companion GUI: {exc}", file=sys.stderr)
        return 1

    app.run()
    return 0


class _TuxCompanionTkApp:
    def __init__(self, *, config: TuxCompanionConfig, tk_module) -> None:
        self.config = config
        self.tk = tk_module
        self.root = tk_module.Tk()
        self.root.title("ARI Tux")
        self.root.configure(bg=TRANSPARENT_COLOR)
        self.root.geometry("+80+120")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self._try_set_transparency()

        self.snapshot = read_tux_companion_snapshot(config)
        self.images = self._load_images(self.snapshot.frames.frame_paths)
        self.frame_index = 0
        self.single_click_after_id: str | None = None

        self.container = tk_module.Frame(self.root, bg=TRANSPARENT_COLOR)
        self.container.pack()

        self.bubble = tk_module.Label(
            self.container,
            text=self.snapshot.bubble_text,
            bg="#111827",
            fg="#f9fafb",
            padx=8,
            pady=5,
            justify="left",
            font=("Helvetica", 11),
            wraplength=260,
        )
        if self.config.show_bubble:
            self.bubble.pack(anchor="w", padx=4, pady=(0, 2))

        self.image_label = tk_module.Label(
            self.container,
            image=self.images[0],
            bg=TRANSPARENT_COLOR,
            bd=0,
            highlightthickness=0,
        )
        self.image_label.pack()
        self.image_label.bind("<Button-1>", self._on_single_click)
        self.image_label.bind("<Double-Button-1>", self._on_double_click)
        self.bubble.bind("<Button-1>", self._on_single_click)
        self.bubble.bind("<Double-Button-1>", self._on_double_click)
        self.root.bind("<Escape>", lambda _event: self.root.destroy())

    def run(self) -> None:
        LOGGER.info("ARI Tux companion running")
        self.root.after(DEFAULT_FRAME_INTERVAL_MS, self._animate)
        self.root.after(int(self.config.poll_interval * 1000), self._poll_status)
        self.root.mainloop()

    def _try_set_transparency(self) -> None:
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT_COLOR)
        except self.tk.TclError:
            LOGGER.debug("Tk transparentcolor attribute is unavailable on this host")
        try:
            self.root.attributes("-alpha", 0.98)
        except self.tk.TclError:
            LOGGER.debug("Tk alpha attribute is unavailable on this host")

    def _load_images(self, frame_paths: tuple[Path, ...]) -> list[object]:
        return [
            self.tk.PhotoImage(file=str(frame_path), master=self.root)
            for frame_path in frame_paths
        ]

    def _animate(self) -> None:
        if self.images:
            self.frame_index = (self.frame_index + 1) % len(self.images)
            self.image_label.configure(image=self.images[self.frame_index])
        self.root.after(DEFAULT_FRAME_INTERVAL_MS, self._animate)

    def _poll_status(self) -> None:
        try:
            snapshot = read_tux_companion_snapshot(self.config)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Unable to refresh ARI Tux status: %s", exc)
            self.root.after(int(self.config.poll_interval * 1000), self._poll_status)
            return

        if snapshot.preview.tux_animation_state != self.snapshot.preview.tux_animation_state:
            self.images = self._load_images(snapshot.frames.frame_paths)
            self.frame_index = 0
            self.image_label.configure(image=self.images[0])
            LOGGER.info(
                "ARI Tux animation changed: %s -> %s",
                self.snapshot.preview.tux_animation_state,
                snapshot.preview.tux_animation_state,
            )

        if snapshot.bubble_text != self.snapshot.bubble_text:
            self.bubble.configure(text=snapshot.bubble_text)

        self.snapshot = snapshot
        self.root.after(int(self.config.poll_interval * 1000), self._poll_status)

    def _on_single_click(self, _event) -> None:
        if self.single_click_after_id is not None:
            self.root.after_cancel(self.single_click_after_id)
        self.single_click_after_id = self.root.after(220, self._toggle_bubble)

    def _on_double_click(self, _event) -> str:
        if self.single_click_after_id is not None:
            self.root.after_cancel(self.single_click_after_id)
            self.single_click_after_id = None
        open_click_target(self.config.click_target)
        return "break"

    def _toggle_bubble(self) -> None:
        self.single_click_after_id = None
        if self.bubble.winfo_ismapped():
            self.bubble.pack_forget()
            return
        self.bubble.pack(anchor="w", padx=4, pady=(0, 2), before=self.image_label)


def open_click_target(click_target: str | None) -> bool:
    if not click_target:
        LOGGER.info("No %s configured.", CLICK_TARGET_ENV)
        print(f"No {CLICK_TARGET_ENV} configured.")
        return False
    LOGGER.info("Opening ARI Tux click target: %s", click_target)
    return webbrowser.open(click_target)


def _frame_sort_key(path: Path) -> tuple[int, str]:
    try:
        return (int(path.stem), path.name)
    except ValueError:
        return (10_000, path.name)


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
