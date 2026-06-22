"""add approval workflow state"""

import sqlalchemy as sa
from alembic import op

revision = "20260422_0005"
down_revision = "20260422_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orchestration_runs",
        sa.Column("controller_cycle_state", sa.String(length=32), nullable=True),
    )

    op.create_table(
        "pending_approvals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("decision_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision_summary", sa.Text(), nullable=False),
        sa.Column("proposed_action", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_pending_approvals_run_id"),
    )
    op.create_index(
        "ix_pending_approvals_status",
        "pending_approvals",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_pending_approvals_requested_at",
        "pending_approvals",
        ["requested_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pending_approvals_requested_at", table_name="pending_approvals")
    op.drop_index("ix_pending_approvals_status", table_name="pending_approvals")
    op.drop_table("pending_approvals")
    op.drop_column("orchestration_runs", "controller_cycle_state")
