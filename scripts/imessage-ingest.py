#!/usr/bin/env python3
"""
Read new messages from your self-message iMessage thread (the one you
use as a personal notes channel) and hand each one to ARI's brain
(ari_core.brain), which understands the text, grounds itself in real
ARI state, and decides what to do — file a task, save a link for
later, ask a clarifying question, or answer a question about your
state. See ari_core/brain.py for the actual decision logic; this
script is just the iMessage plumbing around it.

This is a self-message thread, so every message belongs to you
regardless of which device sent it — messages composed on your phone
show up as "received" from this Mac's point of view, so direction is
ignored entirely.

Run from ~/Code/ari with the venv active:
  python scripts/imessage-ingest.py [--dry-run]

In --dry-run mode, the brain still runs for real (so you can see what
it would do), but no open loop is actually created/resolved, no link
is actually saved, no iMessage is actually sent, and no state (cursor,
conversation history) is persisted.

Idempotent: tracks the last processed message ROWID and the rolling
conversation history in the conversation_states Postgres table (channel
"imessage"), so state survives restarts/crashes with real transactional
guarantees instead of ad hoc JSON files.

Your self-conversation can be split across more than one chat in
Messages' database — e.g. once under your phone number, once under
your Apple ID email — depending on which identity composed a given
message. This script watches all configured identifiers and replies
into whichever thread a message actually came from, so the
conversation stays coherent on your device.

Requires:
  - ARI_IMESSAGE_TO: your own phone number/Apple ID (primary self-thread)
  - ARI_IMESSAGE_SELF_IDENTIFIERS: comma-separated list of every identifier
    your self-thread might appear under (phone + Apple ID email). Falls back
    to just ARI_IMESSAGE_TO if unset.
  - ANTHROPIC_API_KEY: for the brain to actually think
  - Automation permission for Messages.app, to send replies

This script never touches ~/Library/Messages/chat.db directly, and never
needs Full Disk Access. Confirmed by direct testing (2026-06-19): macOS's
TCC check for a process several hops below launchd attributes Full Disk
Access to the top-level process launchd spawned, not to whichever leaf
binary actually opens the file — a launchd -> bash -> sqlite3 chain was
denied even with sqlite3 itself individually granted FDA, while
launchd -> sqlite3 directly succeeded. So the privileged read is its own
launchd job (com.ari.imessage-dump.plist) whose ProgramArguments invoke
/usr/bin/sqlite3 as launchd's literal direct child — nothing else in
between. That job dumps the self-thread to state/imessage-dump.tsv every
60s; this script just reads that plain file. Full Disk Access is granted
to /usr/bin/sqlite3 only, forever, regardless of Python/Homebrew/venv
upgrades.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

sys.path.extend([
    str(REPO_ROOT / "packages" / "ari-state" / "src"),
    str(REPO_ROOT / "packages" / "ari-memory" / "src"),
    str(REPO_ROOT / "packages" / "ari-events" / "src"),
    str(REPO_ROOT / "packages" / "ari-routines" / "src"),
    str(REPO_ROOT / "packages" / "ari-signals" / "src"),
    str(REPO_ROOT / "packages" / "ari-cli" / "src"),
    str(REPO_ROOT / "services" / "ari-core" / "src"),
    str(REPO_ROOT / "services" / "ari-api" / "src"),
    str(REPO_ROOT / "services" / "ari-hub" / "src"),
])

from _ari_common import exit_if_already_running, exit_if_paused, run_guarded  # noqa: E402
from _imessage import send_imessage  # noqa: E402
from ari_core import (  # noqa: E402
    build_mcp_request_args,
    get_conversation_state,
    make_tool_dispatcher,
    record_skill_invocation,
    respond_to_message,
    save_conversation_state,
)
from ari_memory import DatabaseSettings, create_engine, create_session_factory  # noqa: E402

DUMP_FILE = REPO_ROOT / "state" / "imessage-dump.tsv"
DUMP_FIELD_SEP = "|"
DUMP_STALE_AFTER = timedelta(minutes=5)  # com.ari.imessage-dump runs every 60s
CONVERSATION_CHANNEL = "imessage"
WATCH_LATER_LOG = REPO_ROOT / "logs" / "watch-later.md"

IMESSAGE_TO = os.environ.get("ARI_IMESSAGE_TO")
SELF_IDENTIFIERS = [
    s.strip()
    for s in os.environ.get("ARI_IMESSAGE_SELF_IDENTIFIERS", IMESSAGE_TO or "").split(",")
    if s.strip()
]

URL_RE = re.compile(r"https?://\S+")
PRINTABLE_RUN_RE = re.compile(r"[\x20-\x7e]{4,}")
LEADING_JUNK_RE = re.compile(r"^[^A-Za-z0-9]+")
OBJECT_REPLACEMENT_CHAR = "￼"
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
MAX_HISTORY_MESSAGES = 40

# Framework noise that shows up as printable runs inside an attributedBody
# NSKeyedArchiver blob — not part of the actual message text.
ATTRIBUTED_BODY_NOISE = {
    "streamtyped",
    "NSAttributedString",
    "NSObject",
    "NSString",
    "NSMutableString",
    "NSMutableAttributedString",
    "NSDictionary",
    "NSMutableDictionary",
    "NSArray",
    "NSNumber",
    "NSValue",
    "__kIMMessagePartAttributeName",
    "__kIMDataDetectedAttributeName",
    "__kIMLinkAttributeName",
}


def _apple_time_to_datetime(value: int) -> datetime:
    if value > 10**12:  # nanoseconds (macOS Mojave+)
        return APPLE_EPOCH + timedelta(seconds=value / 1e9)
    return APPLE_EPOCH + timedelta(seconds=value)  # older macOS: seconds


def _extract_from_attributed_body(blob: bytes) -> str | None:
    # attributedBody is an NSKeyedArchiver blob (used whenever a message
    # isn't plain unstyled text — links, mentions, many recent macOS
    # versions even for ordinary text). Rather than implement a full
    # unarchiver, pull every printable run out of the raw bytes, drop the
    # known framework class-name/key noise, and take the longest survivor —
    # in practice that's the actual message body.
    decoded = blob.decode("latin-1")
    candidates = [
        run for run in PRINTABLE_RUN_RE.findall(decoded) if run not in ATTRIBUTED_BODY_NOISE
    ]
    if not candidates:
        return None
    best = max(candidates, key=len)
    return LEADING_JUNK_RE.sub("", best).strip() or None


def _extract_text(text: str | None, attributed_body: bytes | None) -> str | None:
    candidate = text or (_extract_from_attributed_body(attributed_body) if attributed_body else None)
    if not candidate:
        return None
    cleaned = candidate.replace(OBJECT_REPLACEMENT_CHAR, "").strip()
    return cleaned or None


def _read_dump_rows() -> list[list[str]]:
    # The privileged read lives entirely in com.ari.imessage-dump.plist,
    # which runs /usr/bin/sqlite3 as launchd's direct child (see module
    # docstring for why that placement is required) and writes a full
    # snapshot of the self-thread to DUMP_FILE every 60s. This process just
    # reads that plain file — it never needs Full Disk Access at all.
    if not DUMP_FILE.exists():
        raise RuntimeError(
            f"{DUMP_FILE} does not exist — is the com.ari.imessage-dump "
            "launchd job loaded?"
        )
    age = datetime.now(tz=UTC) - datetime.fromtimestamp(DUMP_FILE.stat().st_mtime, tz=UTC)
    if age > DUMP_STALE_AFTER:
        raise RuntimeError(
            f"{DUMP_FILE} is {age} old — com.ari.imessage-dump appears to have "
            "stopped running. Check logs/imessage-dump.log."
        )
    with DUMP_FILE.open(encoding="utf-8") as f:
        return [line.rstrip("\n").split(DUMP_FIELD_SEP) for line in f if line.strip()]


def _fetch_new_messages(*, identifiers: list[str], since_rowid: int) -> list[dict]:
    del identifiers  # the dump is already pre-filtered to the self-thread
    messages = []
    for rowid, text_hex, body_hex, date, chat_identifier, assoc_type in _read_dump_rows():
        rowid = int(rowid)
        if rowid <= since_rowid:
            continue
        messages.append(
            {
                "rowid": rowid,
                "text": bytes.fromhex(text_hex).decode("utf-8") if text_hex else None,
                "attributed_body": bytes.fromhex(body_hex) if body_hex else None,
                "date": int(date) if date else 0,
                "chat_identifier": chat_identifier,
                "associated_message_type": int(assoc_type) if assoc_type else 0,
            }
        )
    messages.sort(key=lambda m: m["rowid"])
    return messages


def _log_watch_later(*, link: str, note: str | None) -> None:
    WATCH_LATER_LOG.parent.mkdir(parents=True, exist_ok=True)
    occurred_at = datetime.now(tz=UTC).isoformat()
    suffix = f" — {note}" if note else ""
    with WATCH_LATER_LOG.open("a", encoding="utf-8") as f:
        f.write(f"- [{occurred_at}] {link}{suffix}\n")


def _recent_sent_texts(history: list[dict], limit: int = 8) -> set[str]:
    # Self-thread messages are indistinguishable by direction (everything is
    # "from me"), so the only reliable way to recognize ARI's own reply
    # coming back as if it were new input from Alec is by matching its exact
    # text against what we actually just sent — not by rowid bookkeeping.
    # rowid-based "advance past our own reply" cannot work here: the
    # privileged dump (com.ari.imessage-dump) only refreshes every 60s, so
    # the cursor can never see a just-sent reply's rowid in time, and a
    # stale-cursor approach causes a self-sustaining echo loop (confirmed
    # in production on 2026-06-19 — see AGENTS.md).
    texts = []
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    t = block.get("text", "").strip()
                    if t:
                        texts.append(t)
        if len(texts) >= limit:
            break
    return set(texts)


def run(*, dry_run: bool = False) -> None:
    if not SELF_IDENTIFIERS:
        print("ARI_IMESSAGE_TO or ARI_IMESSAGE_SELF_IDENTIFIERS must be set.")
        return

    engine = create_engine(DatabaseSettings().database_url)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        existing_state = get_conversation_state(session, channel=CONVERSATION_CHANNEL)
    since_rowid = existing_state.cursor if existing_state else 0
    history = existing_state.messages if existing_state else []

    messages = _fetch_new_messages(identifiers=SELF_IDENTIFIERS, since_rowid=since_rowid)
    if not messages:
        print("No new messages.")
        return

    def save_for_later(link: str, note: str | None) -> None:
        print(f"  WATCH-LATER: {link}" + (f" ({note})" if note else ""))
        _log_watch_later(link=link, note=note)

    dispatch_tool = make_tool_dispatcher(
        session_factory, save_for_later=save_for_later, dry_run=dry_run
    )

    def get_mcp_request_args() -> tuple[list[dict], list[dict]]:
        with session_factory() as session:
            return build_mcp_request_args(session)

    def log_invocation(
        skill_kind, skill_name: str, tool_name: str, summary: str, payload: dict, is_error: bool
    ) -> None:
        # Audit rows are observability, not user-facing state, but a
        # --dry-run preview run shouldn't leave real audit history behind
        # any more than it leaves a real open loop behind — same reasoning
        # as the dry_run gates inside make_tool_dispatcher.
        if dry_run:
            return
        with session_factory() as session:
            record_skill_invocation(
                session,
                channel=CONVERSATION_CHANNEL,
                skill_kind=skill_kind,
                skill_name=skill_name,
                tool_name=tool_name,
                summary=summary,
                payload=payload,
                is_error=is_error,
            )

    max_rowid = since_rowid
    replies_sent = 0
    processed = 0
    skipped_echoes = 0
    recent_sent = _recent_sent_texts(history)

    for msg in messages:
        max_rowid = max(max_rowid, msg["rowid"])

        if msg["associated_message_type"]:
            # tapback reaction (Liked/Loved/etc.), not a real message
            continue

        text = _extract_text(msg["text"], msg["attributed_body"])
        if not text:
            print(f"  SKIP (no text): rowid {msg['rowid']}")
            continue

        if text in recent_sent:
            print(f"  SKIP (echo of own reply): {text[:60]!r}")
            skipped_echoes += 1
            continue

        processed += 1
        print(f"  IN: {text}")
        result = respond_to_message(
            text=text,
            history=history,
            dispatch_tool=dispatch_tool,
            get_mcp_request_args=get_mcp_request_args,
            log_invocation=log_invocation,
        )
        history = result.messages

        if result.reply:
            print(f"  OUT: {result.reply}")
            if not dry_run:
                send_imessage(msg["chat_identifier"], result.reply)
                replies_sent += 1
                recent_sent.add(result.reply)
        else:
            print("  OUT: (no reply)")

    if not dry_run:
        trimmed_history = history[-MAX_HISTORY_MESSAGES:]
        with session_factory() as session:
            save_conversation_state(
                session,
                channel=CONVERSATION_CHANNEL,
                cursor=max_rowid,
                messages=trimmed_history,
            )

    print(f"\nProcessed {processed} message(s), sent {replies_sent} reply/replies, skipped {skipped_echoes} echo(es).")


if __name__ == "__main__":
    exit_if_paused("imessage-ingest")
    with exit_if_already_running("imessage-ingest"):
        run_guarded("imessage-ingest", run, dry_run="--dry-run" in sys.argv)
