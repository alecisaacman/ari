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
from ari_core.content_production import move
from ari_core.modules.self_documentation.library import content_view, edit_script, get_content_item
from ari_core.script_review import review as review_script
from fastapi.responses import FileResponse
from ari_core.panel import HUB_CHANNEL, build_panel, recent_exchange
from ari_core.self_review import Write as ReviewWriter
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker


class BrainMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class ContentStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=32)


class ScriptEditRequest(BaseModel):
    hook: str = Field(min_length=1, max_length=300)
    beats: list[str] = Field(min_length=1, max_length=12)
    caption: str = Field(default="", max_length=600)


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

    @app.get("/content")
    def get_content() -> dict[str, Any]:
        return content_view(db_path=spine_db_path())

    @app.post("/content/{item_id}/status")
    def post_content_status(item_id: str, payload: ContentStatusRequest) -> dict[str, Any]:
        try:
            item, producing = move(item_id, payload.status, db_path=spine_db_path())
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if item is None:
            raise HTTPException(status_code=404, detail="No such content item.")
        return {**item.to_dict(), "producing": producing}

    @app.get("/content/{item_id}/video")
    def get_content_video(item_id: str) -> FileResponse:
        item = get_content_item(item_id, db_path=spine_db_path())
        path = Path(str((item.video or {}).get("path", ""))) if item else None
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail="No video for that item yet.")
        return FileResponse(path, media_type="video/mp4")

    @app.put("/content/{item_id}/scripts/{number}")
    def put_content_script(item_id: str, number: int, payload: ScriptEditRequest) -> dict[str, Any]:
        try:
            item = edit_script(item_id, number - 1, hook=payload.hook, beats=payload.beats, caption=payload.caption,
                               db_path=spine_db_path())
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if item is None:
            raise HTTPException(status_code=404, detail="No such content item.")
        return item.to_dict()

    @app.post("/content/{item_id}/review")
    def post_content_review(item_id: str) -> dict[str, Any]:
        with session_factory() as session:
            try:
                return review_script(session, item_id, db_path=spine_db_path()).to_dict()
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error

