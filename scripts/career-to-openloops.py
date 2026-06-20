#!/usr/bin/env python3
"""
Sync career opportunities from openai-dev-sandbox into ARI as OpenLoop records.

Sources:
  - ~/Code/openai-dev-sandbox/data/remote_cashflow.sqlite (PACKET_READY, REVIEWED)
  - ~/Code/openai-dev-sandbox/data/career_tracker.csv (manually tracked)

Run from ~/Code/ari with the venv active:
  python scripts/career-to-openloops.py

Safe to run repeatedly — idempotent via source key deduplication.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SANDBOX = Path.home() / "Code" / "openai-dev-sandbox"

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

from ari_core import CreateOpenLoopInput, create_open_loop, list_open_loops  # noqa: E402
from ari_memory import DatabaseSettings, create_engine, create_session_factory  # noqa: E402
from ari_state import OpenLoopKind, OpenLoopPriority  # noqa: E402

from _ari_common import exit_if_paused  # noqa: E402

SOURCE_KEY = "career_command_center"
ACTIVE_STATUSES = {"PACKET_READY", "REVIEWED"}
TERMINAL_STATUSES = {"rejected", "withdrew", "closed", "archived"}


def _build_loop_key(company: str, role: str) -> str:
    return f"career:{company.lower().replace(' ', '-')}:{role.lower().replace(' ', '-')[:40]}"


def _load_sqlite_opportunities() -> list[dict]:
    db_path = SANDBOX / "data" / "remote_cashflow.sqlite"
    if not db_path.exists():
        print(f"  SKIP: remote_cashflow.sqlite not found at {db_path}")
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT title, company, status, url, updated_at FROM opportunities "
        "WHERE status IN ('PACKET_READY','REVIEWED') ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _load_csv_opportunities() -> list[dict]:
    csv_path = SANDBOX / "data" / "career_tracker.csv"
    if not csv_path.exists():
        print(f"  SKIP: career_tracker.csv not found at {csv_path}")
        return []
    with open(csv_path, newline="") as f:
        return [r for r in csv.DictReader(f)
                if r.get("status", "").lower() not in TERMINAL_STATUSES]


def sync(*, dry_run: bool = False) -> None:
    engine = create_engine(DatabaseSettings().database_url)
    session_factory = create_session_factory(engine)

    # Load existing open loops to find already-synced ones
    with session_factory() as session:
        existing = list_open_loops(session)
    existing_sources = {
        loop.notes.split("source_key:")[-1].split(" | ")[0].strip()
        for loop in existing
        if "source_key:" in (loop.notes or "")
    }

    created = 0
    skipped = 0
    total_candidates = 0

    # --- SQLite opportunities ---
    sqlite_opps = _load_sqlite_opportunities()
    print(f"SQLite candidates: {len(sqlite_opps)} (PACKET_READY / REVIEWED)")
    for opp in sqlite_opps:
        total_candidates += 1
        company = opp["company"]
        role = opp["title"]
        status = opp["status"]
        source_key = _build_loop_key(company, role)

        if source_key in existing_sources:
            skipped += 1
            continue
        existing_sources.add(source_key)

        priority = OpenLoopPriority.HIGH if status == "PACKET_READY" else OpenLoopPriority.MEDIUM
        notes = f"status: {status} | source_key:{source_key}"
        if opp.get("url"):
            notes += f" | url: {opp['url']}"

        print(f"  {'[DRY RUN] ' if dry_run else ''}CREATE [{priority}] {company} — {role}")

        if not dry_run:
            loop_input = CreateOpenLoopInput(
                title=f"Application: {company} — {role}",
                source=SOURCE_KEY,
                kind=OpenLoopKind.TASK,
                priority=priority,
                notes=notes,
            )
            with session_factory() as session:
                create_open_loop(session, loop=loop_input, opened_at=datetime.now(tz=UTC))
        created += 1

    # --- CSV opportunities ---
    csv_opps = _load_csv_opportunities()
    print(f"\nCSV candidates: {len(csv_opps)} (non-terminal)")
    for opp in csv_opps:
        total_candidates += 1
        company = opp.get("company", "").strip()
        role = opp.get("role", "").strip()
        if not company or not role:
            continue
        source_key = _build_loop_key(company, role)

        if source_key in existing_sources:
            skipped += 1
            continue
        existing_sources.add(source_key)

        score_str = opp.get("overall_score", "")
        try:
            score = float(score_str)
            priority = OpenLoopPriority.HIGH if score >= 7.5 else OpenLoopPriority.MEDIUM
        except (ValueError, TypeError):
            priority = OpenLoopPriority.MEDIUM

        notes_parts = [f"source_key:{source_key}"]
        if opp.get("recommendation"):
            notes_parts.append(f"rec: {opp['recommendation']}")
        if opp.get("next_action"):
            notes_parts.append(f"next: {opp['next_action']}")
        notes = " | ".join(notes_parts)

        print(f"  {'[DRY RUN] ' if dry_run else ''}CREATE [{priority}] {company} — {role}")

        if not dry_run:
            loop_input = CreateOpenLoopInput(
                title=f"Application: {company} — {role}",
                source=SOURCE_KEY,
                kind=OpenLoopKind.TASK,
                priority=priority,
                notes=notes,
            )
            with session_factory() as session:
                create_open_loop(session, loop=loop_input, opened_at=datetime.now(tz=UTC))
        created += 1

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Summary: "
          f"{created} created, {skipped} skipped (already synced), "
          f"{total_candidates - created - skipped} other")


if __name__ == "__main__":
    exit_if_paused("career-to-openloops")

    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN — no records will be written\n")
    sync(dry_run=dry_run)
