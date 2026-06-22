from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from ari_telegram_gateway.event_builder import TelegramEventBuilder
from ari_telegram_gateway.persistence import TelegramEventStore

SAMPLE_UPDATE = {
    "update_id": 10001,
    "message": {
        "message_id": 501,
        "date": 1_776_640_000,
        "from": {
            "id": 123456789,
            "is_bot": False,
            "first_name": "Authorized",
            "username": "ari_owner",
        },
        "chat": {
            "id": 123456789,
            "first_name": "Authorized",
            "username": "ari_owner",
            "type": "private",
        },
        "text": "Codex needs to inspect why dashboard buttons disappeared",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a Telegram-like payload into a structured ARI event."
    )
    parser.add_argument(
        "--payload",
        type=Path,
        help="Optional JSON file containing a Telegram update.",
    )
    parser.add_argument("--inbox-dir", type=Path, help="Override ARI_TELEGRAM_INBOX_DIR.")
    parser.add_argument("--events-dir", type=Path, help="Override ARI_TELEGRAM_EVENTS_DIR.")
    parser.add_argument(
        "--authorized-user-id",
        help="Authorized sender ID for the smoke conversion. Defaults to the payload sender.",
    )
    args = parser.parse_args()

    update = _load_payload(args.payload)
    sender_id = str(update["message"]["from"]["id"])
    bot_identity = os.environ.get("ARI_TELEGRAM_BOT_IDENTITY", "ari_command")

    temp_path = Path(tempfile.mkdtemp(prefix="ari-telegram-smoke-"))
    inbox_dir = args.inbox_dir or _env_path("ARI_TELEGRAM_INBOX_DIR") or temp_path / "inbox"
    events_dir = args.events_dir or _env_path("ARI_TELEGRAM_EVENTS_DIR") or temp_path / "events"
    authorized_user_id = args.authorized_user_id or sender_id
    store = TelegramEventStore(inbox_dir=inbox_dir, events_dir=events_dir)
    builder = TelegramEventBuilder(
        bot_identity=bot_identity,
        authorized_telegram_user_id=authorized_user_id,
        bot_id="smoke-bot-id",
        bot_username="AriCommandBot",
    )

    store.save_raw_update(update)
    event = builder.build_from_update(update)
    event_path = store.save_event(event)
    if event.pending_codex_task is not None:
        store.save_codex_task(event.pending_codex_task, event_id=event.event_id)

    print(json.dumps(event.model_dump(mode="json"), indent=2, sort_keys=True))
    print(f"structured_event_path={event_path}")

    return 0


def _load_payload(path: Path | None) -> dict[str, object]:
    if path is None:
        return SAMPLE_UPDATE
    return json.loads(path.read_text(encoding="utf-8"))


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else None


if __name__ == "__main__":
    raise SystemExit(main())
