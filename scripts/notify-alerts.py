#!/usr/bin/env python3
"""
Deliver unsent ELEVATED or INTERRUPTIVE alerts from today's latest
orchestration run via iMessage (if ARI_IMESSAGE_TO is set), falling
back to a macOS notification otherwise. Marks each delivered alert's
sent_at.

Run from ~/Code/ari with the venv active:
  python scripts/notify-alerts.py [--state-date YYYY-MM-DD]

Called automatically by daily-check.sh after orchestration.

iMessage delivery sends from the Apple ID already signed into
Messages.app on this Mac, to your own number/handle (a self-message
thread, separate from your other conversations) — Apple does not
allow a second simultaneous iMessage account on one device, so a
dedicated "ARI" identity isn't possible here. Requires:
  - ARI_IMESSAGE_TO: your own phone number or Apple ID
  - Automation permission granted (System Settings > Privacy & Security >
    Automation) for whatever process runs this script to control Messages.app
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, date, datetime
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

from ari_core import get_latest_run_details  # noqa: E402
from ari_memory import DatabaseSettings, create_engine, create_session_factory  # noqa: E402
from ari_memory.tables import AlertRow  # noqa: E402
from ari_state import AlertEscalationLevel  # noqa: E402

from _imessage import send_imessage  # noqa: E402
from _ari_common import exit_if_paused, run_guarded  # noqa: E402

NOTIFY_LEVELS = {AlertEscalationLevel.ELEVATED, AlertEscalationLevel.INTERRUPTIVE}

IMESSAGE_TO = os.environ.get("ARI_IMESSAGE_TO")


def _deliver(title: str, message: str) -> None:
    body = f"{title}\n{message}" if message else title
    if IMESSAGE_TO:
        if send_imessage(IMESSAGE_TO, body):
            return
        print("  iMessage delivery failed, falling back to system notification.")
    _notify(title, message)


def _notify(title: str, message: str) -> None:
    script = (
        f'display notification {_osa_str(message)} '
        f'with title {_osa_str("ARI")} '
        f'subtitle {_osa_str(title)}'
    )
    subprocess.run(["osascript", "-e", script], check=False)


def _osa_str(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def run(*, state_date: date) -> None:
    engine = create_engine(DatabaseSettings().database_url)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        details = get_latest_run_details(session, state_date=state_date)
        if details is None:
            print(f"No orchestration run found for {state_date}.")
            return

        pending = [
            a for a in details.alerts
            if a.escalation_level in NOTIFY_LEVELS and a.sent_at is None
        ]

        if not pending:
            print(f"No unsent elevated/interruptive alerts for {state_date}.")
            return

        now = datetime.now(tz=UTC)
        for alert in pending:
            print(f"  NOTIFY [{alert.escalation_level}] {alert.title}")
            _deliver(alert.title, alert.message or alert.reason or "")
            row = session.get(AlertRow, alert.id)
            if row is not None:
                row.sent_at = now

        session.commit()
        print(f"Sent {len(pending)} notification(s) and marked as sent.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        if not IMESSAGE_TO:
            print("ARI_IMESSAGE_TO must be set for --test.")
            sys.exit(1)
        ok = send_imessage(IMESSAGE_TO, "This is a test message from ARI.")
        print("iMessage send OK." if ok else "iMessage send FAILED.")
        sys.exit(0 if ok else 1)

    exit_if_paused("notify-alerts")

    target_date = date.today()
    for arg in sys.argv[1:]:
        if arg.startswith("--state-date="):
            target_date = date.fromisoformat(arg.split("=", 1)[1])
        elif arg == "--state-date" and sys.argv.index(arg) + 1 < len(sys.argv):
            target_date = date.fromisoformat(sys.argv[sys.argv.index(arg) + 1])
    run_guarded("notify-alerts", run, state_date=target_date)
