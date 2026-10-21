"""Read the self-thread snapshot written by the privileged dump job.

Only `/usr/bin/sqlite3`, run by launchd as its direct child, ever opens
~/Library/Messages/chat.db (see `launchd.py` for why). It writes the newest
messages of the self-thread to a plain file; this module only reads that file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

FIELD_SEPARATOR = "|"
PRINTABLE_RUN_RE = re.compile(r"[\x20-\x7e]{4,}")
LEADING_JUNK_RE = re.compile(r"^[^A-Za-z0-9]+")
OBJECT_REPLACEMENT_CHAR = "￼"

# Framework noise that shows up as printable runs inside an attributedBody
# NSKeyedArchiver blob; not part of the message text.
ATTRIBUTED_BODY_NOISE = frozenset(
    {
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
)


@dataclass(frozen=True, slots=True)
class DumpRow:
    rowid: int
    text: str | None
    chat_identifier: str
    is_tapback: bool


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
        rowid, text_hex, body_hex, _date, chat_identifier, associated_type = fields
        text = bytes.fromhex(text_hex).decode("utf-8", errors="replace") if text_hex else None
        body = bytes.fromhex(body_hex) if body_hex else None
        rows.append(
            DumpRow(
                rowid=int(rowid),
                text=extract_text(text, body),
                chat_identifier=chat_identifier,
                # Tapbacks (Liked, Loved, ...) carry a nonzero associated type.
                is_tapback=bool(associated_type) and associated_type != "0",
            )
        )
    return sorted(rows, key=lambda row: row.rowid)


def extract_text(text: str | None, attributed_body: bytes | None) -> str | None:
    candidate = text or (_from_attributed_body(attributed_body) if attributed_body else None)
    if not candidate:
        return None
    cleaned = candidate.replace(OBJECT_REPLACEMENT_CHAR, "").strip()
    return cleaned or None


def _from_attributed_body(blob: bytes) -> str | None:
    # attributedBody is an NSKeyedArchiver blob, used for links, mentions, and on
    # recent macOS often for plain text. The longest printable run that is not
    # framework noise is, in practice, the message body.
    decoded = blob.decode("latin-1")
    candidates = [run for run in PRINTABLE_RUN_RE.findall(decoded) if run not in ATTRIBUTED_BODY_NOISE]
    if not candidates:
        return None
    return LEADING_JUNK_RE.sub("", max(candidates, key=len)).strip() or None
