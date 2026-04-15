import argparse
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from .db import (
    add_contact,
    add_followup,
    add_note,
    complete_followup,
    contact_exists,
    followup_exists,
    get_contact,
    initialize_database,
    list_contacts,
    list_due_followups,
    list_followups,
    list_followups_for_contact,
    list_notes_for_contact,
    list_pending_followups,
)
from ...core.paths import DB_PATH


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ari networking",
        description="Networking CRM module inside ARI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create the local SQLite database.")
    subparsers.add_parser("status", help="Show the current local project status.")

    add_contact_parser = subparsers.add_parser("add-contact", help="Add a networking contact.")
    add_contact_parser.add_argument("--name", required=True, help="Full name for the contact.")
    add_contact_parser.add_argument("--company", help="Company name.")
    add_contact_parser.add_argument("--role", dest="role_title", help="Role or title.")
    add_contact_parser.add_argument("--location", help="Location or city.")
    add_contact_parser.add_argument("--source", help="Where you met or found them.")
    add_contact_parser.add_argument("--email", help="Email address.")
    add_contact_parser.add_argument("--linkedin-url", help="LinkedIn profile URL.")

    subparsers.add_parser("list-contacts", help="List saved contacts.")

    add_note_parser = subparsers.add_parser("add-note", help="Attach a note to a contact.")
    add_note_parser.add_argument("--contact-id", type=int, required=True, help="Existing contact id.")
    add_note_parser.add_argument("--body", required=True, help="Note text.")

    add_followup_parser = subparsers.add_parser("add-followup", help="Add a follow-up for a contact.")
    add_followup_parser.add_argument("--contact-id", type=int, required=True, help="Existing contact id.")
    add_followup_parser.add_argument("--due-on", required=True, help="Due date in YYYY-MM-DD format.")
    add_followup_parser.add_argument("--reason", help="Reason or context for the follow-up.")

    subparsers.add_parser("list-followups", help="List saved follow-ups.")
    complete_followup_parser = subparsers.add_parser(
        "complete-followup",
        help="Mark a follow-up as completed.",
    )
    complete_followup_parser.add_argument("--id", type=int, required=True, help="Existing follow-up id.")
    show_contact_parser = subparsers.add_parser("show-contact", help="Show a contact with notes and follow-ups.")
    show_contact_parser.add_argument("--id", type=int, required=True, help="Existing contact id.")
    subparsers.add_parser("due", help="Show overdue and today's pending follow-ups.")
    subparsers.add_parser("today", help="Show today's follow-up summary.")

    return parser


def dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser, db_path: Path = DB_PATH) -> int:
    if args.command == "init-db":
        return handle_init_db(db_path=db_path)
    if args.command == "status":
        return handle_status(db_path=db_path)
    if args.command == "add-contact":
        return handle_add_contact(args, db_path=db_path)
    if args.command == "list-contacts":
        return handle_list_contacts(db_path=db_path)
    if args.command == "add-note":
        return handle_add_note(args, db_path=db_path)
    if args.command == "add-followup":
        return handle_add_followup(args, db_path=db_path)
    if args.command == "list-followups":
        return handle_list_followups(db_path=db_path)
    if args.command == "complete-followup":
        return handle_complete_followup(args, db_path=db_path)
    if args.command == "show-contact":
        return handle_show_contact(args, db_path=db_path)
    if args.command == "due":
        return handle_due(db_path=db_path)
    if args.command == "today":
        return handle_today(db_path=db_path)

    parser.error(f"Unknown command: {args.command}")
    return 2


def handle_init_db(db_path: Path = DB_PATH) -> int:
    db_path = initialize_database(db_path=db_path)
    print(f"Initialized database at {db_path}")
    return 0


def handle_status(db_path: Path = DB_PATH) -> int:
    exists = db_path.exists()
    print("ARI Module: networking-crm")
    print(f"Database: {db_path}")
    print(f"Database initialized: {'yes' if exists else 'no'}")
    print("Primary command: ari networking ...")
    print("Legacy alias: networking-crm ...")
    return 0


def handle_add_contact(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    contact_id = add_contact(
        full_name=args.name,
        company=args.company,
        role_title=args.role_title,
        location=args.location,
        source=args.source,
        email=args.email,
        linkedin_url=args.linkedin_url,
        db_path=db_path,
    )
    print(f"Added contact #{contact_id}: {args.name}")
    return 0


def handle_list_contacts(db_path: Path = DB_PATH) -> int:
    contacts = list_contacts(db_path=db_path)
    if not contacts:
        print("No contacts found.")
        return 0

    for contact in contacts:
        summary_parts = [f"#{contact['id']}", contact["full_name"]]
        if contact["company"]:
            summary_parts.append(contact["company"])
        if contact["role_title"]:
            summary_parts.append(contact["role_title"])
        print(" | ".join(summary_parts))

        detail_parts = []
        if contact["location"]:
            detail_parts.append(f"location={contact['location']}")
        if contact["source"]:
            detail_parts.append(f"source={contact['source']}")
        if contact["email"]:
            detail_parts.append(f"email={contact['email']}")
        if contact["linkedin_url"]:
            detail_parts.append(f"linkedin={contact['linkedin_url']}")
        if detail_parts:
            print(f"  {'; '.join(detail_parts)}")

    return 0


def handle_add_note(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    if not contact_exists(args.contact_id, db_path=db_path):
        print(f"Contact #{args.contact_id} does not exist.")
        return 1

    note_id = add_note(contact_id=args.contact_id, body=args.body, db_path=db_path)
    print(f"Added note #{note_id} to contact #{args.contact_id}")
    return 0


def render_followups(followups: list[object]) -> int:
    for followup in followups:
        summary_parts = [
            f"#{followup['id']}",
            f"contact=#{followup['contact_id']}",
            followup["full_name"],
            f"due={followup['due_on']}",
        ]
        print(" | ".join(summary_parts))

        detail_parts = [f"status={followup['status']}"]
        if followup["reason"]:
            detail_parts.append(f"reason={followup['reason']}")
        print(f"  {'; '.join(detail_parts)}")

    return 0


def handle_add_followup(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    if not contact_exists(args.contact_id, db_path=db_path):
        print(f"Contact #{args.contact_id} does not exist.")
        return 1

    followup_id = add_followup(
        contact_id=args.contact_id,
        due_on=args.due_on,
        reason=args.reason,
        db_path=db_path,
    )
    print(f"Added follow-up #{followup_id} to contact #{args.contact_id}")
    return 0


def handle_list_followups(db_path: Path = DB_PATH) -> int:
    followups = list_followups(db_path=db_path)
    if not followups:
        print("No follow-ups found.")
        return 0

    return render_followups(followups)


def handle_complete_followup(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    if not followup_exists(args.id, db_path=db_path):
        print(f"Follow-up #{args.id} does not exist.")
        return 1

    complete_followup(followup_id=args.id, db_path=db_path)
    print(f"Completed follow-up #{args.id}")
    return 0


def handle_show_contact(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    contact = get_contact(args.id, db_path=db_path)
    if contact is None:
        print(f"Contact #{args.id} does not exist.")
        return 1

    notes = list_notes_for_contact(contact_id=args.id, db_path=db_path)
    followups = list_followups_for_contact(contact_id=args.id, db_path=db_path)

    print(f"Contact #{contact['id']}: {contact['full_name']}")
    detail_fields = (
        ("Company", contact["company"]),
        ("Role", contact["role_title"]),
        ("Location", contact["location"]),
        ("Source", contact["source"]),
        ("Email", contact["email"]),
        ("LinkedIn", contact["linkedin_url"]),
        ("Created", contact["created_at"]),
        ("Updated", contact["updated_at"]),
    )
    for label, value in detail_fields:
        if value:
            print(f"  {label}: {value}")

    print("")
    print("Notes:")
    if not notes:
        print("  None")
    else:
        for note in notes:
            print(f"  - #{note['id']} [{note['created_at']}] {note['body']}")

    print("")
    print("Follow-ups:")
    if not followups:
        print("  None")
    else:
        for followup in followups:
            summary = (
                f"  - #{followup['id']} due={followup['due_on']} "
                f"status={followup['status']}"
            )
            print(summary)
            if followup["reason"]:
                print(f"    reason: {followup['reason']}")
            if followup["completed_at"]:
                print(f"    completed_at: {followup['completed_at']}")

    return 0


def handle_due(db_path: Path = DB_PATH) -> int:
    followups = list_due_followups(today=date.today().isoformat(), db_path=db_path)
    if not followups:
        print("No follow-ups due.")
        return 0

    return render_followups(followups)


def render_today_section(title: str, followups: list[object]) -> None:
    print(title)
    if not followups:
        print("  none")
        return

    for followup in followups:
        summary_parts = [
            f"contact=#{followup['contact_id']}",
            followup["full_name"],
            f"due={followup['due_on']}",
        ]
        if followup["reason"]:
            summary_parts.append(f"reason={followup['reason']}")
        print(f"  {' | '.join(summary_parts)}")


def handle_today(db_path: Path = DB_PATH) -> int:
    today_value = date.today()
    today_iso = today_value.isoformat()
    upcoming_cutoff = today_value + timedelta(days=7)
    upcoming_cutoff_iso = upcoming_cutoff.isoformat()
    pending_followups = list_pending_followups(db_path=db_path)

    overdue = [followup for followup in pending_followups if followup["due_on"] < today_iso]
    due_today = [followup for followup in pending_followups if followup["due_on"] == today_iso]
    upcoming = [
        followup
        for followup in pending_followups
        if today_iso < followup["due_on"] <= upcoming_cutoff_iso
    ]

    print("Today")
    print(f"Pending follow-ups: {len(pending_followups)}")
    print("")
    render_today_section("Overdue", overdue)
    print("")
    render_today_section("Due Today", due_today)
    print("")
    render_today_section("Upcoming (Next 7 Days)", upcoming)
    return 0


def main(argv: Optional[List[str]] = None, db_path: Path = DB_PATH) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return dispatch(args, parser, db_path=db_path)


if __name__ == "__main__":
    raise SystemExit(main())
