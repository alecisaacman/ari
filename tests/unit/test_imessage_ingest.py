"""Regression coverage for the iMessage self-thread echo bug: ARI's own
just-sent reply re-appearing as "new" input on a later poll cycle (the
privileged dump only refreshes every 60s, so rowid-based "advance past our
own reply" cannot work — see AGENTS.md). _recent_sent_texts is the fix:
content-based recognition of ARI's own recent replies, independent of
rowid/dump timing."""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_module():
    sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        "imessage_ingest_test_target", SCRIPTS_DIR / "imessage-ingest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


def test_recent_sent_texts_extracts_assistant_text_blocks() -> None:
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": [{"type": "text", "text": "Got it."}]},
        {"role": "user", "content": [{"type": "tool_result", "content": "..."}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Filed: buy milk"}]},
    ]
    assert mod._recent_sent_texts(history) == {"Got it.", "Filed: buy milk"}


def test_recent_sent_texts_ignores_non_text_assistant_blocks() -> None:
    history = [
        {
            "role": "assistant",
            "content": [
                {"type": "server_tool_use", "id": "x", "input": {"query": "weather"}},
                {"type": "web_search_tool_result", "content": []},
            ],
        },
    ]
    assert mod._recent_sent_texts(history) == set()


def test_recent_sent_texts_respects_limit() -> None:
    history = [
        {"role": "assistant", "content": [{"type": "text", "text": f"reply {i}"}]}
        for i in range(10)
    ]
    result = mod._recent_sent_texts(history, limit=3)
    assert len(result) == 3
    # most recent ones (closest to the end of history) should be kept
    assert "reply 9" in result
    assert "reply 0" not in result


def test_recent_sent_texts_empty_history() -> None:
    assert mod._recent_sent_texts([]) == set()
