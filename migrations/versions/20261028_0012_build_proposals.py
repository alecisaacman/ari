"""keep the builds ARI proposes for itself and what Alec decided"""

import sqlalchemy as sa
from alembic import op

revision = "20261028_0012"
down_revision = "20261028_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "build_proposals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column("brief", sa.Text(), nullable=False),
        sa.Column("skill_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="proposed"),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_build_proposals_status", "build_proposals", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_build_proposals_status", table_name="build_proposals")
    op.drop_table("build_proposals")
