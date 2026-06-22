from __future__ import annotations

import json

from ari_telegram_gateway.event_builder import TelegramEventBuilder
from ari_telegram_gateway.models import (
    AgentRole,
    EventStatus,
    IntentType,
    MediaStatus,
    TranscriptStatus,
)
from ari_telegram_gateway.persistence import TelegramEventStore


def test_event_creation_for_authorized_codex_task(tmp_path) -> None:
    update = _telegram_update("Codex needs to inspect why dashboard buttons disappeared")
    builder = TelegramEventBuilder(
        bot_identity="ari_command",
        authorized_telegram_user_id="42",
        bot_id="bot-1",
        bot_username="AriCommandBot",
    )
    store = TelegramEventStore(inbox_dir=tmp_path / "inbox", events_dir=tmp_path / "events")

    event = builder.build_from_update(update)
    event_path = store.save_event(event)
    task_path = store.save_codex_task(event.pending_codex_task, event_id=event.event_id)

    assert event.source == "telegram"
    assert event.bot_identity == "ari_command"
    assert event.conversation_id == "42"
    assert event.sender_id == "42"
    assert event.authorized is True
    assert event.normalized_intent is IntentType.CODEX_TASK
    assert event.assigned_role is AgentRole.CTO_CODEX
    assert event.requires_approval is True
    assert event.pending_codex_task is not None
    assert event.pending_codex_task.approval_required is True
    assert event.pending_codex_task.target_repo_or_system == "ari-hub"
    assert json.loads(event_path.read_text(encoding="utf-8"))["event_id"] == event.event_id
    assert json.loads(task_path.read_text(encoding="utf-8"))["event_id"] == event.event_id


def test_unauthorized_sender_is_rejected_without_codex_task() -> None:
    update = _telegram_update("Codex should fix the repo", sender_id=99)
    builder = TelegramEventBuilder(
        bot_identity="ari_command",
        authorized_telegram_user_id="42",
    )

    event = builder.build_from_update(update)

    assert event.authorized is False
    assert event.status is EventStatus.REJECTED
    assert event.assigned_role is AgentRole.OPERATOR
    assert event.normalized_intent is IntentType.UNKNOWN
    assert event.next_action == "reject_unauthorized_sender"
    assert event.pending_codex_task is None


def test_instagram_link_event_does_not_claim_media_access() -> None:
    update = _telegram_update("This competitor reel matters https://instagram.com/reel/abc123/")
    builder = TelegramEventBuilder(
        bot_identity="ari_command",
        authorized_telegram_user_id="42",
    )

    event = builder.build_from_update(update)

    assert event.assigned_role is AgentRole.CPO
    assert event.normalized_intent is IntentType.COMPETITOR_INTEL
    assert event.source_platform == "instagram"
    assert event.media_status is MediaStatus.LINK_ONLY
    assert event.transcript_status is TranscriptStatus.UNAVAILABLE
    assert event.assets[0].kind == "link"
    assert event.assets[0].media_status is MediaStatus.LINK_ONLY
    assert event.assets[0].transcript_status is TranscriptStatus.UNAVAILABLE


def test_video_payload_creates_captured_asset_with_pending_transcript() -> None:
    update = _telegram_update(
        "CPO, save this as design inspiration",
        extra_message={
            "video": {
                "file_id": "video-file-id",
                "file_unique_id": "video-unique-id",
                "file_name": "inspiration.mp4",
                "mime_type": "video/mp4",
                "file_size": 2048,
            }
        },
    )
    builder = TelegramEventBuilder(
        bot_identity="ari_command",
        authorized_telegram_user_id="42",
    )

    event = builder.build_from_update(update)

    assert event.assigned_role is AgentRole.CPO
    assert event.normalized_intent is IntentType.PRODUCT_INSPIRATION
    assert event.media_status is MediaStatus.CAPTURED
    assert event.transcript_status is TranscriptStatus.PENDING
    assert event.assets[0].kind == "video"
    assert event.assets[0].local_path is None
    assert event.assets[0].transcript_status is TranscriptStatus.PENDING


def _telegram_update(
    text: str,
    *,
    sender_id: int = 42,
    extra_message: dict[str, object] | None = None,
) -> dict[str, object]:
    message: dict[str, object] = {
        "message_id": 10,
        "date": 1_776_640_000,
        "from": {
            "id": sender_id,
            "is_bot": False,
            "first_name": "ARI",
            "username": "ari_owner",
        },
        "chat": {
            "id": sender_id,
            "type": "private",
        },
        "text": text,
    }
    if extra_message:
        message.update(extra_message)
    return {
        "update_id": 100,
        "message": message,
    }
