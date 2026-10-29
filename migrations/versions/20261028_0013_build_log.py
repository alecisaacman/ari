"""keep a log of every release: what changed and why"""

import sqlalchemy as sa
from alembic import op

revision = "20261028_0013"
down_revision = "20261028_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "build_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("release", sa.String(length=64), nullable=False),
        sa.Column("commit", sa.String(length=64), nullable=False),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("commits", sa.JSON(), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release"),
    )
    op.create_index("ix_build_log_shipped_at", "build_log", ["shipped_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_build_log_shipped_at", table_name="build_log")
    op.drop_table("build_log")
