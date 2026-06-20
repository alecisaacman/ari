"""add open_loops.company and open_loop_enrichments"""

from alembic import op
import sqlalchemy as sa

revision = "20260619_0008"
down_revision = "20260619_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("open_loops", sa.Column("company", sa.String(length=255), nullable=True))

    op.create_table(
        "open_loop_enrichments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("loop_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_open_loop_enrichments_loop_id",
        "open_loop_enrichments",
        ["loop_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_open_loop_enrichments_loop_id", table_name="open_loop_enrichments")
    op.drop_table("open_loop_enrichments")
    op.drop_column("open_loops", "company")
