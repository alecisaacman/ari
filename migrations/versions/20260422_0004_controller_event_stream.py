"""add controller event stream"""

from alembic import op
import sqlalchemy as sa

revision = "20260422_0004"
down_revision = "20260422_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "controller_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "sequence_number",
            name="uq_controller_events_run_id_sequence_number",
        ),
    )
    op.create_index(
        "ix_controller_events_run_id",
        "controller_events",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_controller_events_occurred_at",
        "controller_events",
        ["occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_controller_events_occurred_at", table_name="controller_events")
    op.drop_index("ix_controller_events_run_id", table_name="controller_events")
    op.drop_table("controller_events")
