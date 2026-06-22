from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class TelegramGatewayConfig:
    telegram_bot_token: str
    authorized_telegram_user_id: str
    inbox_dir: Path
    events_dir: Path
    polling_state_file: Path
    bot_identity: str
    polling_timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> TelegramGatewayConfig:
        load_dotenv()
        token = _required_env("TELEGRAM_BOT_TOKEN")
        authorized_user_id = _required_env("AUTHORIZED_TELEGRAM_USER_ID")
        inbox_dir = Path(_required_env("ARI_TELEGRAM_INBOX_DIR")).expanduser()
        events_dir = Path(_required_env("ARI_TELEGRAM_EVENTS_DIR")).expanduser()
        bot_identity = _required_env("ARI_TELEGRAM_BOT_IDENTITY")
        polling_state_file = Path(
            os.environ.get(
                "ARI_TELEGRAM_POLLING_STATE_FILE",
                f"data/telegram/state/{_safe_identity(bot_identity)}_polling_state.json",
            )
        ).expanduser()
        timeout = int(os.environ.get("ARI_TELEGRAM_POLLING_TIMEOUT_SECONDS", "30"))

        return cls(
            telegram_bot_token=token,
            authorized_telegram_user_id=authorized_user_id,
            inbox_dir=inbox_dir,
            events_dir=events_dir,
            polling_state_file=polling_state_file,
            bot_identity=bot_identity,
            polling_timeout_seconds=timeout,
        )


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _safe_identity(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in {"_", "-"} else "_"
        for character in value
    )
    return safe.strip("_") or "telegram_bot"
