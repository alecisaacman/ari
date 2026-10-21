"""add brain_usage for per-request model cost"""

import sqlalchemy as sa
from alembic import op

revision = "20261020_0009"
down_revision = "20260619_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brain_usage",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("web_searches", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_microusd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("escalated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_brain_usage_occurred_at", "brain_usage", ["occurred_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_brain_usage_occurred_at", table_name="brain_usage")
    op.drop_table("brain_usage")
