from __future__ import annotations

import json
import shutil
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class TelegramApiError(RuntimeError):
    pass


class TelegramBotClient:
    def __init__(self, token: str) -> None:
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._file_base_url = f"https://api.telegram.org/file/bot{token}"

    def get_me(self) -> dict[str, Any]:
        return self._api("getMe")

    def get_updates(self, *, offset: int | None = None, timeout: int = 30) -> list[dict[str, Any]]:
        payload: dict[str, object] = {
            "timeout": timeout,
            "allowed_updates": json.dumps(["message", "edited_message"]),
        }
        if offset is not None:
            payload["offset"] = offset
        result = self._api("getUpdates", payload)
        if not isinstance(result, list):
            raise TelegramApiError("Telegram getUpdates returned a non-list result")
        return [item for item in result if isinstance(item, dict)]

    def get_file(self, file_id: str) -> dict[str, Any]:
        result = self._api("getFile", {"file_id": file_id})
        if not isinstance(result, dict):
            raise TelegramApiError("Telegram getFile returned a non-object result")
        return result

    def download_file(self, file_path: str, destination: Path) -> None:
        if not file_path:
            raise TelegramApiError("Telegram file path is missing")
        url = f"{self._file_base_url}/{urllib.parse.quote(file_path)}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as response:
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output)

    def send_message(self, *, chat_id: str, text: str) -> None:
        self._api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
        )

    def _api(self, method: str, payload: dict[str, object] | None = None) -> object:
        data = None
        headers = {}
        if payload is not None:
            data = urllib.parse.urlencode(payload).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(f"{self._base_url}/{method}", data=data, headers=headers)
        with urllib.request.urlopen(request, timeout=70) as response:
            raw = json.loads(response.read().decode("utf-8"))
        if not isinstance(raw, dict) or not raw.get("ok"):
            raise TelegramApiError(f"Telegram API call failed for {method}")
        return raw.get("result")
