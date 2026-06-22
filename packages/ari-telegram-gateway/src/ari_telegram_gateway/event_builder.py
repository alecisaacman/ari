from __future__ import annotations

from typing import Any

from ari_telegram_gateway.classifier import INSTAGRAM_PATTERN, classify_message
from ari_telegram_gateway.models import (
    AgentRole,
    EventStatus,
    InboundAsset,
    IntentType,
    MediaStatus,
    PendingCodexTask,
    RiskLevel,
    TelegramInboundEvent,
    TranscriptStatus,
)


class TelegramEventBuilder:
    def __init__(
        self,
        *,
        bot_identity: str,
        authorized_telegram_user_id: str,
        bot_id: str | None = None,
        bot_username: str | None = None,
    ) -> None:
        self.bot_identity = bot_identity
        self.authorized_telegram_user_id = str(authorized_telegram_user_id)
        self.bot_id = bot_id
        self.bot_username = bot_username

    def build_from_update(self, update: dict[str, Any]) -> TelegramInboundEvent:
        message = self._extract_message(update)
        sender = self._dict(message.get("from"))
        chat = self._dict(message.get("chat"))
        sender_id = str(sender.get("id", ""))
        authorized = sender_id == self.authorized_telegram_user_id
        raw_text = self._raw_text(message)

        if not authorized:
            return TelegramInboundEvent(
                bot_identity=self.bot_identity,
                bot_id=self.bot_id,
                bot_username=self.bot_username,
                conversation_id=str(chat.get("id", "")),
                conversation_type=_optional_str(chat.get("type")),
                sender_id=sender_id,
                sender_username=_optional_str(sender.get("username")),
                sender_display_name=self._sender_display_name(sender),
                authorized=False,
                raw_text=raw_text,
                normalized_intent=IntentType.UNKNOWN,
                assigned_role=AgentRole.OPERATOR,
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                assets=[],
                status=EventStatus.REJECTED,
                next_action="reject_unauthorized_sender",
                raw_update_id=_optional_int(update.get("update_id")),
                raw_message_id=_optional_int(message.get("message_id")),
                raw_message=self._safe_raw_message(message),
            )

        assets = self._assets_from_message(message)
        media_kinds = [asset.kind for asset in assets if asset.kind != "link"]
        classification = classify_message(
            raw_text,
            has_media=bool(media_kinds),
            media_kinds=media_kinds,
        )
        assets = self._apply_classification_to_assets(assets, classification.media_status)
        pending_codex_task = None
        if classification.assigned_role is AgentRole.CTO_CODEX:
            pending_codex_task = self._pending_codex_task(raw_text)

        return TelegramInboundEvent(
            bot_identity=self.bot_identity,
            bot_id=self.bot_id,
            bot_username=self.bot_username,
            conversation_id=str(chat.get("id", "")),
            conversation_type=_optional_str(chat.get("type")),
            sender_id=sender_id,
            sender_username=_optional_str(sender.get("username")),
            sender_display_name=self._sender_display_name(sender),
            authorized=True,
            raw_text=raw_text,
            normalized_intent=classification.normalized_intent,
            assigned_role=classification.assigned_role,
            risk_level=classification.risk_level,
            requires_approval=classification.requires_approval,
            assets=assets,
            status=EventStatus.RECEIVED,
            next_action=classification.next_action,
            source_platform=classification.source_platform,
            media_status=classification.media_status,
            transcript_status=classification.transcript_status,
            pending_codex_task=pending_codex_task,
            raw_update_id=_optional_int(update.get("update_id")),
            raw_message_id=_optional_int(message.get("message_id")),
            raw_message=self._safe_raw_message(message),
        )

    def _extract_message(self, update: dict[str, Any]) -> dict[str, Any]:
        for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
            candidate = update.get(key)
            if isinstance(candidate, dict):
                return candidate
        return {}

    def _raw_text(self, message: dict[str, Any]) -> str:
        text = message.get("text")
        caption = message.get("caption")
        if isinstance(text, str):
            return text.strip()
        if isinstance(caption, str):
            return caption.strip()
        return ""

    def _assets_from_message(self, message: dict[str, Any]) -> list[InboundAsset]:
        assets: list[InboundAsset] = []
        assets.extend(self._link_assets(self._raw_text(message)))

        photo = message.get("photo")
        if isinstance(photo, list) and photo:
            largest_photo = max(
                (item for item in photo if isinstance(item, dict)),
                key=lambda item: int(item.get("file_size", 0) or 0),
                default=None,
            )
            if largest_photo is not None:
                assets.append(
                    InboundAsset(
                        kind="photo",
                        telegram_file_id=_optional_str(largest_photo.get("file_id")),
                        telegram_file_unique_id=_optional_str(largest_photo.get("file_unique_id")),
                        file_size=_optional_int(largest_photo.get("file_size")),
                        media_status=MediaStatus.CAPTURED,
                    )
                )

        for kind in ("video", "document", "voice"):
            payload = message.get(kind)
            if isinstance(payload, dict):
                assets.append(self._file_asset(kind, payload))

        return assets

    def _file_asset(self, kind: str, payload: dict[str, Any]) -> InboundAsset:
        transcript_status = (
            TranscriptStatus.PENDING if kind in {"video", "voice"} else TranscriptStatus.NONE
        )
        return InboundAsset(
            kind=kind,
            telegram_file_id=_optional_str(payload.get("file_id")),
            telegram_file_unique_id=_optional_str(payload.get("file_unique_id")),
            original_file_name=_optional_str(payload.get("file_name")),
            mime_type=_optional_str(payload.get("mime_type")),
            file_size=_optional_int(payload.get("file_size")),
            media_status=MediaStatus.CAPTURED,
            transcript_status=transcript_status,
        )

    def _link_assets(self, raw_text: str) -> list[InboundAsset]:
        assets: list[InboundAsset] = []
        for match in INSTAGRAM_PATTERN.finditer(raw_text):
            assets.append(
                InboundAsset(
                    kind="link",
                    source_url=match.group(0),
                    source_platform="instagram",
                    media_status=MediaStatus.LINK_ONLY,
                    transcript_status=TranscriptStatus.UNAVAILABLE,
                )
            )
        return assets

    def _apply_classification_to_assets(
        self, assets: list[InboundAsset], media_status: MediaStatus
    ) -> list[InboundAsset]:
        if media_status is not MediaStatus.LINK_ONLY:
            return assets
        return [
            asset.model_copy(update={"media_status": MediaStatus.LINK_ONLY})
            if asset.kind == "link"
            else asset
            for asset in assets
        ]

    def _pending_codex_task(self, raw_text: str) -> PendingCodexTask:
        goal = raw_text.strip() or "Inspect the code-related Telegram request."
        return PendingCodexTask(
            goal=goal,
            target_repo_or_system=_infer_target_repo_or_system(goal),
            risk_level=RiskLevel.MEDIUM,
            proposed_next_step=(
                "Create a bounded Codex work item for approval; after approval, inspect the "
                "target repo/system and report the smallest safe next action."
            ),
            approval_required=True,
        )

    def _safe_raw_message(self, message: dict[str, Any]) -> dict[str, object]:
        allowed_keys = {
            "message_id",
            "date",
            "chat",
            "from",
            "text",
            "caption",
            "photo",
            "video",
            "document",
            "voice",
        }
        return {key: value for key, value in message.items() if key in allowed_keys}

    def _dict(self, value: object) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _sender_display_name(self, sender: dict[str, Any]) -> str | None:
        parts = [
            _optional_str(sender.get("first_name")),
            _optional_str(sender.get("last_name")),
        ]
        display = " ".join(part for part in parts if part).strip()
        return display or None


def _infer_target_repo_or_system(goal: str) -> str | None:
    text = " ".join(goal.lower().split())
    if "dashboard" in text or "hub" in text or "ace" in text:
        return "ari-hub"
    if "api" in text:
        return "ari-api"
    if "repo" in text or "code" in text or "codex" in text:
        return "ari-canonical"
    return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
