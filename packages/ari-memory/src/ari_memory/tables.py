from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import UUID as SQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DailyStateRow(Base):
    __tablename__ = "daily_states"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    priorities: Mapped[list[str]] = mapped_column(JSON, default=list)
    win_condition: Mapped[str] = mapped_column(Text, default="")
    movement: Mapped[bool | None] = mapped_column(nullable=True)
    stress: Mapped[int | None] = mapped_column(nullable=True)
    next_action: Mapped[str] = mapped_column(Text, default="")
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WeeklyStateRow(Base):
    __tablename__ = "weekly_states"

    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    outcomes: Mapped[list[str]] = mapped_column(JSON, default=list)
    cannot_drift: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers: Mapped[list[str]] = mapped_column(JSON, default=list)
    lesson: Mapped[str] = mapped_column(Text, default="")
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OpenLoopRow(Base):
    __tablename__ = "open_loops"

    id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="open")
    kind: Mapped[str] = mapped_column(String(32), default="task")
    priority: Mapped[str] = mapped_column(String(32), default="medium")
    source: Mapped[str] = mapped_column(String(64))
    notes: Mapped[str] = mapped_column(Text, default="")
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_id: Mapped[UUID | None] = mapped_column(SQLUUID(as_uuid=True), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_touched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OpenLoopEnrichmentRow(Base):
    __tablename__ = "open_loop_enrichments"
    __table_args__ = (Index("ix_open_loop_enrichments_loop_id", "loop_id"),)

    id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), primary_key=True)
    loop_id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(64))
    company: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text, default="")
    findings: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


class SignalRow(Base):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint(
            "state_date",
            "fingerprint",
            name="uq_signals_state_date_fingerprint",
        ),
    )

    id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), primary_key=True)
    state_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    related_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_entity_id: Mapped[UUID | None] = mapped_column(SQLUUID(as_uuid=True), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertRow(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint(
            "state_date",
            "fingerprint",
            name="uq_alerts_state_date_fingerprint",
        ),
    )

    id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), primary_key=True)
    state_date: Mapped[date] = mapped_column(Date)
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    channel: Mapped[str] = mapped_column(String(32))
    escalation_level: Mapped[str] = mapped_column(String(32), default="visible")
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    source_signal_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrchestrationRunRow(Base):
    __tablename__ = "orchestration_runs"

    id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), primary_key=True)
    state_date: Mapped[date] = mapped_column(Date)
    state_fingerprint: Mapped[str] = mapped_column(String(64))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signal_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    alert_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    controller_trajectory: Mapped[dict[str, object] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    controller_cycle_state: Mapped[str | None] = mapped_column(String(32), nullable=True)


class PendingApprovalRow(Base):
    __tablename__ = "pending_approvals"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            name="uq_pending_approvals_run_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True))
    decision_id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    decision_summary: Mapped[str] = mapped_column(Text)
    proposed_action: Mapped[str] = mapped_column(Text)


class ConversationStateRow(Base):
    __tablename__ = "conversation_states"
    __table_args__ = (UniqueConstraint("channel", name="uq_conversation_states_channel"),)

    id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), primary_key=True)
    channel: Mapped[str] = mapped_column(String(64))
    cursor: Mapped[int] = mapped_column(BigInteger, default=0)
    messages: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ControllerEventRow(Base):
    __tablename__ = "controller_events"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "sequence_number",
            name="uq_controller_events_run_id_sequence_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True))
    sequence_number: Mapped[int]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_type: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class SkillRegistrationRow(Base):
    __tablename__ = "skill_registrations"
    __table_args__ = (UniqueConstraint("name", name="uq_skill_registrations_name"),)

    id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32), default="mcp")
    mcp_url: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    encrypted_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SkillInvocationRow(Base):
    __tablename__ = "skill_invocations"
    __table_args__ = (
        Index("ix_skill_invocations_occurred_at", "occurred_at"),
        Index("ix_skill_invocations_skill_name", "skill_name"),
    )

    id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str] = mapped_column(String(64))
    skill_kind: Mapped[str] = mapped_column(String(32))
    skill_name: Mapped[str] = mapped_column(String(64))
    tool_name: Mapped[str] = mapped_column(String(128))
    summary: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
