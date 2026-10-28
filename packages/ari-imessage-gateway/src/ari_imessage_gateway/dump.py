"""Read the self-thread snapshot written by the privileged dump job.

Only `/usr/bin/sqlite3`, run by launchd as its direct child, ever opens
~/Library/Messages/chat.db (see `launchd.py` for why). It writes the newest
messages of the self-thread to a plain file; this module only reads that file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

FIELD_SEPARATOR = "|"
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
OBJECT_REPLACEMENT_CHAR = "￼"


@dataclass(frozen=True, slots=True)
class DumpRow:
    rowid: int
    text: str | None
    chat_identifier: str
    is_tapback: bool
    sent_at: datetime | None = None


class DumpUnavailable(RuntimeError):
    """The snapshot is missing or stale, so the dump job is not running."""


def read_dump(path: Path, *, stale_after: timedelta, now: datetime | None = None) -> list[DumpRow]:
    if not path.exists():
        raise DumpUnavailable(f"{path} does not exist; is the iMessage dump job loaded?")
    current = now or datetime.now(tz=UTC)
    age = current - datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    if age > stale_after:
        raise DumpUnavailable(f"{path} is {age} old; the iMessage dump job has stopped.")
    rows: list[DumpRow] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split(FIELD_SEPARATOR)
        if len(fields) != 6 or not fields[0].isdigit():
            continue
        rowid, text_hex, body_hex, apple_date, chat_identifier, associated_type = fields
        text = bytes.fromhex(text_hex).decode("utf-8", errors="replace") if text_hex else None
        body = bytes.fromhex(body_hex) if body_hex else None
        rows.append(
            DumpRow(
                rowid=int(rowid),
                text=extract_text(text, body),
                chat_identifier=chat_identifier,
                # Tapbacks (Liked, Loved, ...) carry a nonzero associated type.
                is_tapback=bool(associated_type) and associated_type != "0",
                sent_at=_apple_time(apple_date),
            )
        )
    return sorted(rows, key=lambda row: row.rowid)


def _apple_time(raw: str) -> datetime | None:
    """Messages stores time since 2001-01-01 UTC, in nanoseconds on current macOS."""
    if not raw.lstrip("-").isdigit() or int(raw) <= 0:
        return None
    value = int(raw)
    return APPLE_EPOCH + timedelta(seconds=value / 1e9 if value > 10**12 else value)


def extract_text(text: str | None, attributed_body: bytes | None) -> str | None:
    candidate = text or (_from_attributed_body(attributed_body) if attributed_body else None)
    if not candidate:
        return None
    cleaned = candidate.replace(OBJECT_REPLACEMENT_CHAR, "").strip()
    return cleaned or None


def _from_attributed_body(blob: bytes) -> str | None:
    """Read the message string out of an attributedBody typedstream blob.

    The string follows the NSString class reference and a "+" marker, prefixed by
    its byte length: one byte below 0x80, or 0x81 then a 16-bit little-endian
    length, or 0x82 then a 32-bit one. Reading by that length matters: a guess
    that keeps the length byte turns "Nothing ..." (length 106) into "jNothing
    ...", which no longer matches ARI's own reply and gets answered. Anything
    that doesn't parse is treated as having no text.
    """
    marker = blob.find(b"NSString")
    if marker < 0:
        return None
    plus = blob.find(b"+", marker + len(b"NSString"), marker + len(b"NSString") + 8)
    if plus < 0 or plus + 1 >= len(blob):
        return None
    position = plus + 1
    prefix = blob[position]
    if prefix < 0x80:
        length, position = prefix, position + 1
    elif prefix == 0x81:
        length, position = int.from_bytes(blob[position + 1 : position + 3], "little"), position + 3
    elif prefix == 0x82:
        length, position = int.from_bytes(blob[position + 1 : position + 5], "little"), position + 5
    else:
        return None
    raw = blob[position : position + length]
    if len(raw) != length:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
