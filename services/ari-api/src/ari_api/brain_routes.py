"""ARI's brain over HTTP, for the hub.

The hub is a window into ARI, not a second brain: it shows ARI's control panel and
carries Alec's messages to the same conversation logic iMessage uses.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ari_core.action_desk import ActionDesk
from ari_core.apple import AppleDesk
from ari_core.brain import respond_to_message
from ari_core.conversation import Conversation, Respond
from ari_core.core import paths as core_paths
from ari_core.panel import HUB_CHANNEL, build_panel, recent_exchange
from ari_core.self_review import Write as ReviewWriter
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker


class BrainMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


def default_action_desk() -> ActionDesk | None:
    try:
        return ActionDesk()
    except ValueError:
        return None  # no permitted workspace: the brain can't propose actions


def register_brain_routes(
    app: FastAPI,
    session_factory: sessionmaker[Session],
    *,
    action_desk: Callable[[], ActionDesk | None] = default_action_desk,
    respond: Respond = respond_to_message,
    spine_db_path: Callable[[], Path] = lambda: core_paths.DB_PATH,
    apple: Callable[[], AppleDesk | None] = AppleDesk.connected,
    review_writer: ReviewWriter | None = None,
) -> None:
    @app.get("/brain/panel")
    def get_brain_panel() -> dict[str, Any]:
        with session_factory() as session:
            return build_panel(
                session, spine_db_path=spine_db_path(), action_desk=action_desk(), apple=apple()
            )

    @app.post("/brain/messages")
    def post_brain_message(payload: BrainMessageRequest) -> dict[str, Any]:
        text = payload.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required.")
        conversation = Conversation(
            channel=HUB_CHANNEL,
            session_factory=session_factory,
            action_desk=action_desk(),
            respond=respond,
            apple=apple(),
            review_writer=review_writer,
        )
        turn = conversation.say(text)
        with session_factory() as session:
            exchange = recent_exchange(session, channel=HUB_CHANNEL)
        return {"reply": turn.reply, "conversation": exchange}
