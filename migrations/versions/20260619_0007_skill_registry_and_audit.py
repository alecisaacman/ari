"""add skill registry and skill invocation audit log"""

import sqlalchemy as sa
from alembic import op

revision = "20260619_0007"
down_revision = "20260619_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skill_registrations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("mcp_url", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("encrypted_token", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_skill_registrations_name"),
    )

    op.create_table(
        "skill_invocations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("skill_kind", sa.String(length=32), nullable=False),
        sa.Column("skill_name", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("is_error", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_skill_invocations_occurred_at",
        "skill_invocations",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_skill_invocations_skill_name",
        "skill_invocations",
        ["skill_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_skill_invocations_skill_name", table_name="skill_invocations")
    op.drop_index("ix_skill_invocations_occurred_at", table_name="skill_invocations")
    op.drop_table("skill_invocations")
    op.drop_table("skill_registrations")
