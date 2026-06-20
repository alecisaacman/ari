"""Shared utilities for ARI's automation scripts: the kill switch check
every entry point must honor, a consistent way to make sure a crash shows
up loudly in logs instead of disappearing silently, and a lock so a
scheduled run and a manually-triggered run of the same script can never
process the same input twice concurrently."""
from __future__ import annotations

import fcntl
import sys
import traceback
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAUSED_FILE = REPO_ROOT / "state" / "PAUSED"
LOCK_DIR = REPO_ROOT / "state" / "locks"


def _ts() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def exit_if_paused(script_name: str) -> None:
    """Call at the very top of every automation entry point. Exits the
    process immediately if scripts/ari-killswitch.sh has been run."""
    if PAUSED_FILE.exists():
        print(f"[{_ts()}] [{script_name}] PAUSED ({PAUSED_FILE}) — exiting without action.")
        sys.exit(0)


@contextmanager
def exit_if_already_running(script_name: str):
    """Use as a context manager around an entry point's main work. If
    another instance of this same script is already mid-run (e.g. a
    launchd-scheduled fire overlapping a manually triggered one, or a slow
    run still finishing when the next interval fires), this instance exits
    immediately instead of racing the other on the same cursor/state —
    confirmed necessary by a real race during 2026-06-19 testing, where two
    concurrent runs both read the same conversation cursor and both
    processed the same message."""
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_DIR / f"{script_name}.lock"
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"[{_ts()}] [{script_name}] another instance is already running — exiting.")
        fd.close()
        sys.exit(0)
    try:
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


def run_guarded(script_name: str, fn, *args, **kwargs):
    """Run fn(*args, **kwargs), guaranteeing that any exception is logged
    with a full traceback and a greppable FAILED marker before the process
    exits non-zero — instead of launchd's log just showing nothing or a
    truncated stack."""
    print(f"[{_ts()}] [{script_name}] starting")
    try:
        result = fn(*args, **kwargs)
        print(f"[{_ts()}] [{script_name}] OK")
        return result
    except Exception:
        print(f"[{_ts()}] [{script_name}] FAILED")
        traceback.print_exc()
        sys.exit(1)
