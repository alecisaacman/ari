from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import UUID as SQLUUID
from sqlalchemy import Date, DateTime, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DailyStateRow(Base):
    __tablename__ = "daily_states"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    priorities: Mapped[list[str]] = mapped_column(JSON, default=list)
    win_condition: Mapped[str] = mapped_column(Text, default="")
    movement: Mapped[Optional[bool]] = mapped_column(nullable=True)
    stress: Mapped[Optional[int]] = mapped_column(nullable=True)
    next_action: Mapped[str] = mapped_column(Text, default="")
    last_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class WeeklyStateRow(Base):
    __tablename__ = "weekly_states"

    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    outcomes: Mapped[list[str]] = mapped_column(JSON, default=list)
    cannot_drift: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers: Mapped[list[str]] = mapped_column(JSON, default=list)
    lesson: Mapped[str] = mapped_column(Text, default="")
    last_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class OpenLoopRow(Base):
    __tablename__ = "open_loops"

    id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="open")
    kind: Mapped[str] = mapped_column(String(32), default="task")
    priority: Mapped[str] = mapped_column(String(32), default="medium")
    source: Mapped[str] = mapped_column(String(64))
    notes: Mapped[str] = mapped_column(Text, default="")
    project_id: Mapped[Optional[UUID]] = mapped_column(SQLUUID(as_uuid=True), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_touched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32), default="capture")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    normalized_text: Mapped[str] = mapped_column(Text, default="")
