"""initial schema"""

from alembic import op
import sqlalchemy as sa

revision = "20260410_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_states",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("priorities", sa.JSON(), nullable=False),
        sa.Column("win_condition", sa.Text(), nullable=False, server_default=""),
        sa.Column("movement", sa.Boolean(), nullable=True),
        sa.Column("stress", sa.Integer(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("date"),
    )
    op.create_table(
        "weekly_states",
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("outcomes", sa.JSON(), nullable=False),
        sa.Column("cannot_drift", sa.JSON(), nullable=False),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("lesson", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("week_start"),
    )
    op.create_table(
        "open_loops",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="task"),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_touched_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="capture"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "signals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("related_entity_type", sa.String(length=64), nullable=True),
        sa.Column("related_entity_id", sa.UUID(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column(
            "escalation_level", sa.String(length=32), nullable=False, server_default="visible"
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_signal_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_status", "alerts", ["status"], unique=False)
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"], unique=False)
    op.create_index("ix_events_occurred_at", "events", ["occurred_at"], unique=False)
    op.create_index("ix_open_loops_status", "open_loops", ["status"], unique=False)
    op.create_index("ix_signals_detected_at", "signals", ["detected_at"], unique=False)
    op.create_index("ix_signals_severity", "signals", ["severity"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_signals_severity", table_name="signals")
    op.drop_index("ix_signals_detected_at", table_name="signals")
    op.drop_index("ix_open_loops_status", table_name="open_loops")
    op.drop_index("ix_events_occurred_at", table_name="events")
    op.drop_index("ix_alerts_created_at", table_name="alerts")
    op.drop_index("ix_alerts_status", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("signals")
    op.drop_table("events")
    op.drop_table("open_loops")
    op.drop_table("weekly_states")
    op.drop_table("daily_states")
