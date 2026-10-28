"""Reminders: things Alec asked ARI to tell him at a specific time.

A reminder is ARI's record, kept in ARI's store. When Apple Reminders is connected,
ARI also puts it on Alec's GET DONE list, and Apple delivers it on his iPhone, even while
the Mac sleeps. Otherwise surfaces text the ones that are due; delivering costs nothing,
since no model is called.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from ari_memory.tables import ReminderRow
from sqlalchemy import select
from sqlalchemy.orm import Session

from ari_core.apple import AppleDesk, AppleError

PENDING = "pending"
SENT = "sent"
CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Reminder:
    id: UUID
    text: str
    remind_at: datetime
    status: str
    loop_id: UUID | None
    apple_id: str | None = None

    def describe(self) -> dict[str, str | None]:
        return {
            "id": str(self.id),
            "text": self.text,
            "remind_at": self.remind_at.astimezone().strftime("%a %b %-d, %-I:%M %p"),
            "status": self.status,
            "loop_id": None if self.loop_id is None else str(self.loop_id),
            "delivered_by": "Apple Reminders (GET DONE)" if self.apple_id else "ARI text",
        }


def parse_when(raw: str) -> datetime:
    """An ISO date-time; without an offset it means Alec's local time."""
    when = datetime.fromisoformat(raw.strip())
    if when.tzinfo is None:
        when = when.astimezone()  # interpret as local wall-clock time
    return when.astimezone(UTC)


def set_reminder(
    session: Session,
    *,
    text: str,
    remind_at: datetime,
    now: datetime,
    loop_id: UUID | None = None,
    source: str = "ari.brain",
    apple: AppleDesk | None = None,
) -> Reminder:
    """Record a reminder, and put it in Apple Reminders when that is connected.

    If Apple refuses, the reminder stays ARI's alone and ARI texts it instead.
    """
    if remind_at <= now:
        raise ValueError("That time has already passed.")
    apple_id = None
    if apple is not None:
        try:
            apple_id = apple.add_reminder(text, due=remind_at)["id"]
        except AppleError:
            apple_id = None
    row = ReminderRow(
        id=uuid4(),
        text=text.strip(),
        remind_at=remind_at,
        status=PENDING,
        loop_id=loop_id,
        source=source,
        created_at=now,
        apple_id=apple_id,
    )
    session.add(row)
    session.commit()
    return _to_model(row)


def pending_reminders(session: Session) -> list[Reminder]:
    rows = session.scalars(
        select(ReminderRow).where(ReminderRow.status == PENDING).order_by(ReminderRow.remind_at)
    ).all()
    return [_to_model(row) for row in rows]


def due_reminders(session: Session, *, now: datetime) -> list[Reminder]:
    return [reminder for reminder in pending_reminders(session) if reminder.remind_at <= now]


def cancel_reminder(
    session: Session, reminder_id: UUID, *, apple: AppleDesk | None = None
) -> Reminder | None:
    row = session.get(ReminderRow, reminder_id)
    if row is None or row.status != PENDING:
        return None
    if row.apple_id and apple is not None:
        try:
            apple.remove_reminder(row.apple_id)
        except AppleError:
            pass  # already gone from Reminders; ARI's record is what matters here
    row.status = CANCELLED
    session.commit()
    return _to_model(row)


def mark_sent(session: Session, reminder_id: UUID, *, sent_at: datetime) -> None:
    row = session.get(ReminderRow, reminder_id)
    if row is not None:
        row.status = SENT
        row.sent_at = sent_at
        session.commit()


def _to_model(row: ReminderRow) -> Reminder:
    return Reminder(
        id=row.id,
        text=row.text,
        # SQLite returns naive datetimes; ARI stores UTC.
        remind_at=row.remind_at if row.remind_at.tzinfo else row.remind_at.replace(tzinfo=UTC),
        status=row.status,
        loop_id=row.loop_id,
        apple_id=row.apple_id,
    )
