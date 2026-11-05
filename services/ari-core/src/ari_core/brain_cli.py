"""`ari api brain ...`: ARI's control panel and conversation from the command line.

The hub uses these in its subprocess bridge mode; they match /brain/panel,
/brain/messages, /content, and /content/{id}/status in ari-api.
"""

from __future__ import annotations

import json
from pathlib import Path

from ari_memory import DatabaseSettings, create_engine, create_session_factory

from .action_desk import ActionDesk
from .apple import AppleDesk
from .conversation import Conversation
from .core.env import load_local_env
from .core.paths import DB_PATH
from .content_production import move
from .modules.self_documentation.library import attach_video, content_view, edit_script
from .script_review import review as review_script
from .panel import HUB_CHANNEL, build_panel, recent_exchange
from .self_review import write_with_model


def _session_factory():  # type: ignore[no-untyped-def]
    return create_session_factory(create_engine(DatabaseSettings().database_url))


def _action_desk() -> ActionDesk | None:
    try:
        return ActionDesk()
    except ValueError:
        return None


def handle_api_brain_panel(args, db_path: Path = DB_PATH) -> int:  # type: ignore[no-untyped-def]
    load_local_env()
    with _session_factory()() as session:
        panel = build_panel(session, spine_db_path=db_path, action_desk=_action_desk(), apple=AppleDesk.connected())
    print(json.dumps(panel) if getattr(args, "as_json", False) else json.dumps(panel, indent=2))
    return 0


def handle_api_brain_message(args, db_path: Path = DB_PATH) -> int:  # type: ignore[no-untyped-def]
    del db_path
    load_local_env()
    session_factory = _session_factory()
    turn = Conversation(
        channel=HUB_CHANNEL,
        session_factory=session_factory,
        action_desk=_action_desk(),
        apple=AppleDesk.connected(),
        review_writer=write_with_model,
    ).say(args.text)
    with session_factory() as session:
        payload = {"reply": turn.reply, "conversation": recent_exchange(session, channel=HUB_CHANNEL)}
    print(json.dumps(payload) if getattr(args, "as_json", False) else (turn.reply or ""))
    return 0


def handle_api_content_list(args, db_path: Path = DB_PATH) -> int:  # type: ignore[no-untyped-def]
    del args
    print(json.dumps(content_view(db_path=db_path)))
    return 0


def handle_api_content_status(args, db_path: Path = DB_PATH) -> int:  # type: ignore[no-untyped-def]
    try:
        item, _ = move(args.id, args.status, db_path=db_path)
    except ValueError as error:
        print(json.dumps({"error": str(error)}))
        return 1
    if item is None:
        print(json.dumps({"error": "No such content item."}))
        return 1
    print(json.dumps(item.to_dict()))
    return 0


def handle_api_content_video(args, db_path: Path = DB_PATH) -> int:  # type: ignore[no-untyped-def]
    """Used by ARI's studio to attach a finished video to its item."""
    item = attach_video(args.id, args.path, voice=args.voice, db_path=db_path)
    if item is None:
        print(json.dumps({"error": "No such content item."}))
        return 1
    print(json.dumps(item.to_dict()))
    return 0


def handle_api_content_edit(args, db_path: Path = DB_PATH) -> int:  # type: ignore[no-untyped-def]
    try:
        item = edit_script(args.id, args.script - 1, hook=args.hook, beats=args.beat, caption=args.caption or "",
                           db_path=db_path)
    except ValueError as error:
        print(json.dumps({"error": str(error)}))
        return 1
    if item is None:
        print(json.dumps({"error": "No such content item."}))
        return 1
    print(json.dumps(item.to_dict()))
    return 0


def handle_api_content_review(args, db_path: Path = DB_PATH) -> int:  # type: ignore[no-untyped-def]
    load_local_env()
    with _session_factory()() as session:
        try:
            item = review_script(session, args.id, db_path=db_path)
        except ValueError as error:
            print(json.dumps({"error": str(error)}))
            return 1
    print(json.dumps(item.to_dict()))
    return 0
