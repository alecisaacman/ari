from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from ari_telegram_gateway.models import InboundAsset, TelegramInboundEvent


class TelegramFileClient(Protocol):
    def get_file(self, file_id: str) -> dict[str, object]:
        pass

    def download_file(self, file_path: str, destination: Path) -> None:
        pass


class TelegramAssetSaver:
    def __init__(self, *, events_dir: Path, telegram_client: TelegramFileClient) -> None:
        self.events_dir = events_dir.expanduser()
        self.telegram_client = telegram_client

    def save_assets(self, event: TelegramInboundEvent) -> TelegramInboundEvent:
        saved_assets: list[InboundAsset] = []
        for asset in event.assets:
            if not asset.telegram_file_id:
                saved_assets.append(asset)
                continue
            local_path = self._save_asset(event.event_id, asset)
            saved_assets.append(asset.model_copy(update={"local_path": str(local_path)}))
        return event.model_copy(update={"assets": saved_assets})

    def _save_asset(self, event_id: str, asset: InboundAsset) -> Path:
        telegram_file = self.telegram_client.get_file(asset.telegram_file_id)
        remote_path = str(telegram_file.get("file_path", ""))
        suffix = Path(remote_path).suffix or _suffix_from_name(asset.original_file_name)
        filename = _safe_filename(asset.original_file_name or f"{asset.asset_id}{suffix}")
        if "." not in filename and suffix:
            filename = f"{filename}{suffix}"
        local_path = self.events_dir / "assets" / event_id / filename
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.telegram_client.download_file(remote_path, local_path)
        return local_path


def _safe_filename(value: str) -> str:
    filename = Path(value).name.strip() or "telegram_asset"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", filename)


def _suffix_from_name(value: str | None) -> str:
    if not value:
        return ""
    return Path(value).suffix
