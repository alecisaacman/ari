from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _event_id() -> str:
    return f"evt_{uuid4().hex}"


def _asset_id() -> str:
    return f"asset_{uuid4().hex}"


def _task_id() -> str:
    return f"codex_task_{uuid4().hex}"


class AgentRole(StrEnum):
    CEO = "CEO"
    CPO = "CPO"
    CTO_CODEX = "CTO_CODEX"
    CCO = "CCO"
    RESEARCH = "RESEARCH"
    MEMORY = "MEMORY"
    OPERATOR = "OPERATOR"


class IntentType(StrEnum):
    STRATEGY_DECISION = "strategy_decision"
    PRODUCT_INSPIRATION = "product_inspiration"
    COMPETITOR_INTEL = "competitor_intel"
    CODEX_TASK = "codex_task"
    CONTENT_STRATEGY = "content_strategy"
    RESEARCH_REQUEST = "research_request"
    MEMORY_CAPTURE = "memory_capture"
    OPERATOR_TASK = "operator_task"
    MEDIA_INGEST = "media_ingest"
    UNKNOWN = "unknown"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EventStatus(StrEnum):
    RECEIVED = "received"
    REJECTED = "rejected"


class MediaStatus(StrEnum):
    NONE = "none"
    LINK_ONLY = "link_only"
    CAPTURED = "captured"
    UNAVAILABLE = "unavailable"


class TranscriptStatus(StrEnum):
    NONE = "none"
    UNAVAILABLE = "unavailable"
    PENDING = "pending"


class InboundAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(default_factory=_asset_id)
    kind: str
    telegram_file_id: str | None = None
    telegram_file_unique_id: str | None = None
    original_file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    local_path: str | None = None
    source_url: str | None = None
    source_platform: str | None = None
    media_status: MediaStatus = MediaStatus.NONE
    transcript_status: TranscriptStatus = TranscriptStatus.NONE


class PendingCodexTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(default_factory=_task_id)
    goal: str
    target_repo_or_system: str | None = None
    risk_level: RiskLevel = RiskLevel.MEDIUM
    proposed_next_step: str
    approval_required: bool = True
    status: str = "pending_approval"


class ClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalized_intent: IntentType
    assigned_role: AgentRole
    risk_level: RiskLevel
    requires_approval: bool
    next_action: str
    source_platform: str | None = None
    media_status: MediaStatus = MediaStatus.NONE
    transcript_status: TranscriptStatus = TranscriptStatus.NONE


class TelegramInboundEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=_event_id)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    source: str = "telegram"
    bot_identity: str
    bot_id: str | None = None
    bot_username: str | None = None
    conversation_id: str
    conversation_type: str | None = None
    sender_id: str
    sender_username: str | None = None
    sender_display_name: str | None = None
    authorized: bool
    raw_text: str
    normalized_intent: IntentType
    assigned_role: AgentRole
    risk_level: RiskLevel
    requires_approval: bool
    assets: list[InboundAsset] = Field(default_factory=list)
    status: EventStatus = EventStatus.RECEIVED
    next_action: str
    source_platform: str | None = None
    media_status: MediaStatus = MediaStatus.NONE
    transcript_status: TranscriptStatus = TranscriptStatus.NONE
    pending_codex_task: PendingCodexTask | None = None
    raw_update_id: int | None = None
    raw_message_id: int | None = None
    raw_message: dict[str, object] = Field(default_factory=dict)
