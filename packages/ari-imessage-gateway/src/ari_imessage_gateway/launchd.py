"""The two launchd jobs that make the iMessage surface always on.

macOS attributes a Full Disk Access check to the process launchd started, not
to the binary that opens the file (confirmed on this Mac on 2026-06-19: a
launchd -> bash -> sqlite3 chain was denied with sqlite3 itself granted access;
launchd -> sqlite3 succeeded). So the dump job runs `/usr/bin/sqlite3` as
launchd's direct child, read-only, and only that Apple binary ever needs Full
Disk Access. The poll job only reads the file it writes.

Both jobs also run the moment something changes, so a text is answered in seconds,
not on the next 10-second tick: the dump job watches Messages' database (a new message
anywhere writes to it), and the poll job watches the snapshot the dump writes. The
interval stays as a fallback and for ARI's scheduled work (reminders, reviews).
launchd's default 10-second throttle would undo that, so both lower it.

These are rendered for Alec to review and install; ARI never installs them.
"""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

from .config import ImessageSettings

DUMP_INTERVAL_SECONDS = 10
POLL_INTERVAL_SECONDS = 10
# How soon launchd may start a job again after it ran; its default is 10 seconds.
THROTTLE_SECONDS = 1
DUMP_ROW_LIMIT = 500
OWNER_ONLY_UMASK = 0o077


def dump_query(identifiers: tuple[str, ...]) -> str:
    if not identifiers:
        raise ValueError("Set ARI_IMESSAGE_TO (and ARI_IMESSAGE_SELF_IDENTIFIERS) first.")
    quoted = ",".join("'" + identifier.replace("'", "''") + "'" for identifier in identifiers)
    # The newest messages of the self-thread only; the poller tracks its own cursor.
    return (
        "SELECT * FROM (SELECT m.ROWID, hex(m.text), hex(m.attributedBody), m.date, "
        "c.chat_identifier, m.associated_message_type FROM message m "
        "JOIN chat_message_join cmj ON cmj.message_id = m.ROWID "
        "JOIN chat c ON c.ROWID = cmj.chat_id "
        f"WHERE c.chat_identifier IN ({quoted}) "
        f"ORDER BY m.ROWID DESC LIMIT {DUMP_ROW_LIMIT}) ORDER BY 1 ASC;"
    )


def render_plists(
    settings: ImessageSettings,
    *,
    label_prefix: str,
    source_root: Path,
    python: Path | None = None,
) -> dict[str, bytes]:
    home = Path.home()
    messages_db = home / "Library" / "Messages" / "chat.db"
    logs = settings.state_dir / "logs"
    dump = {
        "Label": f"{label_prefix}.imessage-dump",
        "ProgramArguments": [
            "/usr/bin/sqlite3",
            "-readonly",
            "-cmd",
            f".output '{settings.dump_path}'",
            f"file:{messages_db}?mode=ro",
            dump_query(settings.self_identifiers),
        ],
        "WatchPaths": [str(messages_db), f"{messages_db}-wal"],
        "ThrottleInterval": THROTTLE_SECONDS,
        "StartInterval": DUMP_INTERVAL_SECONDS,
        "RunAtLoad": True,
        # The snapshot holds Alec's messages: owner-only, not launchd's default 022.
        "Umask": OWNER_ONLY_UMASK,
        "StandardOutPath": str(logs / "imessage-dump.log"),
        "StandardErrorPath": str(logs / "imessage-dump.log"),
    }
    poll = {
        "Label": f"{label_prefix}.imessage-poll",
        "ProgramArguments": [str(python or sys.executable), "-m", "ari_imessage_gateway", "poll"],
        "WorkingDirectory": str(source_root),
        "WatchPaths": [str(settings.dump_path)],
        "ThrottleInterval": THROTTLE_SECONDS,
        "StartInterval": POLL_INTERVAL_SECONDS,
        "RunAtLoad": True,
        "Umask": OWNER_ONLY_UMASK,
        "EnvironmentVariables": {"ARI_HOME": str(settings.state_dir.parent)},
        "StandardOutPath": str(logs / "imessage-poll.log"),
        "StandardErrorPath": str(logs / "imessage-poll.log"),
    }
    return {
        f"{dump['Label']}.plist": plistlib.dumps(dump),
        f"{poll['Label']}.plist": plistlib.dumps(poll),
    }
