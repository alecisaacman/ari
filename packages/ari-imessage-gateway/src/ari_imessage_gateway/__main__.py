"""`python -m ari_imessage_gateway` (or `ari-imessage`): run and inspect the iMessage surface."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from pathlib import Path

from ari_core.action_desk import ActionDesk
from ari_core.apple import AppleDesk
from ari_core.core.env import ari_home, load_local_env
from ari_core.core.pause import get_pause_state
from ari_memory import DatabaseSettings, create_engine, create_session_factory

from .config import ImessageSettings
from .dump import DumpUnavailable, read_dump
from .gateway import ImessageGateway
from .launchd import render_plists
from .messages_app import MessagesApp

SOURCE_ROOT = Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ari-imessage", description="ARI's iMessage surface.")
    commands = parser.add_subparsers(dest="command", required=True)
    poll = commands.add_parser("poll", help="Handle new self-thread messages once.")
    poll.add_argument("--dry-run", action="store_true", help="Run the brain; send and save nothing.")
    poll.add_argument("--loop", type=int, metavar="SECONDS", help="Keep polling every N seconds.")
    commands.add_parser("doctor", help="Report what the surface still needs.")
    plists = commands.add_parser("plists", help="Write the launchd jobs for review; installs nothing.")
    plists.add_argument("--out", type=Path, required=True)
    plists.add_argument("--python", type=Path, help="Interpreter the poll job runs (default: this one).")
    plists.add_argument("--source-root", type=Path, help="Where the poll job runs (default: this checkout).")
    commands.add_parser("send-test", help="Send one test message to yourself.")
    args = parser.parse_args(argv)

    load_local_env(ari_home() / "ari.env")
    settings = ImessageSettings.from_env()
    if args.command == "poll":
        return _poll(settings, dry_run=args.dry_run, loop=args.loop)
    if args.command == "doctor":
        return _doctor(settings)
    if args.command == "plists":
        args.out.mkdir(parents=True, exist_ok=True)
        for name, payload in render_plists(
            settings,
            label_prefix=f"com.{getpass.getuser()}.ari",
            source_root=args.source_root or SOURCE_ROOT,
            python=args.python,
        ).items():
            (args.out / name).write_bytes(payload)
            print(args.out / name)
        return 0
    if not settings.reply_to:
        print("Set ARI_IMESSAGE_TO first.")
        return 1
    app = MessagesApp()
    sent = app.send(settings.reply_to, "ARI test message. If you can read this, I can reach you.")
    print("sent" if sent else f"failed: {app.last_error}")
    return 0 if sent else 1


def _gateway(settings: ImessageSettings, *, dry_run: bool) -> ImessageGateway:
    session_factory = create_session_factory(create_engine(DatabaseSettings().database_url))
    try:
        desk: ActionDesk | None = ActionDesk()
    except ValueError:
        desk = None  # no permitted workspace: the brain can't propose actions
    return ImessageGateway(
        settings=settings,
        session_factory=session_factory,
        action_desk=desk,
        dry_run=dry_run,
        apple=AppleDesk.connected(),
    )


def _poll(settings: ImessageSettings, *, dry_run: bool, loop: int | None) -> int:
    gateway = _gateway(settings, dry_run=dry_run)
    while True:
        report = gateway.poll_once()
        if report.status != "ok" or report.handled or report.alerts_sent or report.signals_raised or report.detail:
            print(json.dumps(report.to_dict()), flush=True)
        if loop is None:
            return 0 if report.status in {"ok", "seeded", "busy"} else 1
        time.sleep(loop)


def _doctor(settings: ImessageSettings) -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(
        ("self-thread configured", bool(settings.reply_to), "set" if settings.reply_to else "set ARI_IMESSAGE_TO")
    )
    try:
        read_dump(settings.dump_path, stale_after=settings.stale_after)
        checks.append(("dump job writing", True, str(settings.dump_path)))
    except DumpUnavailable as error:
        checks.append(("dump job writing", False, f"{error} Load the dump job and give /usr/bin/sqlite3 Full Disk Access."))
    credentials = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    checks.append(
        ("brain credentials", credentials, "found" if credentials else "set ANTHROPIC_API_KEY in ARI_HOME/ari.env")
    )
    try:
        ActionDesk()
        checks.append(("workspace for actions", True, os.environ.get("ARI_EXECUTION_ROOT", "")))
    except ValueError as error:
        checks.append(("workspace for actions", False, f"optional: {error}"))
    paused = get_pause_state()["paused"]
    checks.append(("not paused", not paused, "text \"ARI resume\" or run `ari resume`" if paused else "running"))
    checks.append(("state store", True, DatabaseSettings().database_url))
    for name, ok, detail in checks:
        print(f"{'ok  ' if ok else 'MISS'} {name}: {detail}")
    required = {"self-thread configured", "dump job writing", "brain credentials", "not paused"}
    return 0 if all(ok for name, ok, _ in checks if name in required) else 1


if __name__ == "__main__":
    sys.exit(main())
