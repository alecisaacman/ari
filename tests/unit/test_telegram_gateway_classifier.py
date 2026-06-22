from ari_telegram_gateway.classifier import classify_message
from ari_telegram_gateway.models import AgentRole, IntentType, MediaStatus, TranscriptStatus


def test_competitor_reel_routes_to_cpo_competitor_intel() -> None:
    result = classify_message("This competitor reel is important for ACE")

    assert result.assigned_role is AgentRole.CPO
    assert result.normalized_intent is IntentType.COMPETITOR_INTEL
    assert result.requires_approval is False


def test_codex_dashboard_bug_requires_approval() -> None:
    result = classify_message("Codex needs to inspect why dashboard buttons disappeared")

    assert result.assigned_role is AgentRole.CTO_CODEX
    assert result.normalized_intent is IntentType.CODEX_TASK
    assert result.requires_approval is True
    assert result.next_action == "create_pending_codex_task"


def test_explicit_ceo_strategy_routes_to_ceo() -> None:
    result = classify_message("CEO, think through whether this direction is right")

    assert result.assigned_role is AgentRole.CEO
    assert result.normalized_intent is IntentType.STRATEGY_DECISION


def test_remember_routes_to_memory_capture() -> None:
    result = classify_message("Remember this")

    assert result.assigned_role is AgentRole.MEMORY
    assert result.normalized_intent is IntentType.MEMORY_CAPTURE


def test_instagram_link_is_link_only_without_transcript() -> None:
    result = classify_message("Save this https://www.instagram.com/reel/example/")

    assert result.source_platform == "instagram"
    assert result.media_status is MediaStatus.LINK_ONLY
    assert result.transcript_status is TranscriptStatus.UNAVAILABLE
    assert result.next_action == "request_video_file_or_screen_recording_if_needed"


def test_video_file_is_media_ingest_with_pending_transcript() -> None:
    result = classify_message("Review this", has_media=True, media_kinds=["video"])

    assert result.normalized_intent is IntentType.MEDIA_INGEST
    assert result.media_status is MediaStatus.CAPTURED
    assert result.transcript_status is TranscriptStatus.PENDING
