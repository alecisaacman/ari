"""Durable memory for brain conversation channels (e.g. iMessage): the
ingestion cursor and rolling message history that used to live in ad hoc
JSON files under state/. No event-sourcing here deliberately — this is
infrastructure memory for the brain, not canonical explainable state."""
from __future__ import annotations

from datetime import UTC, datetime

from ari_memory import ConversationStateRepository
from ari_state import ConversationState
from sqlalchemy.orm import Session


def get_conversation_state(session: Session, *, channel: str) -> ConversationState | None:
    return ConversationStateRepository(session).get(channel)


def save_conversation_state(
    session: Session,
    *,
    channel: str,
    cursor: int,
    messages: list[dict[str, object]],
) -> ConversationState:
    state = ConversationState(
        channel=channel,
        cursor=cursor,
        messages=messages,
        updated_at=datetime.now(tz=UTC),
    )
    result = ConversationStateRepository(session).upsert(state)
    session.commit()
    return result
