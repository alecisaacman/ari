"""add reminders for messages ARI sends at a set time"""

import sqlalchemy as sa
from alembic import op

revision = "20261028_0010"
down_revision = "20261020_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("loop_id", sa.UUID(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reminders_status_remind_at", "reminders", ["status", "remind_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reminders_status_remind_at", table_name="reminders")
    op.drop_table("reminders")
