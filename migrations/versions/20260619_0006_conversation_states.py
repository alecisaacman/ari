"""add conversation states for brain memory"""

import sqlalchemy as sa
from alembic import op

revision = "20260619_0006"
down_revision = "20260422_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_states",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("cursor", sa.BigInteger(), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel", name="uq_conversation_states_channel"),
    )


def downgrade() -> None:
    op.drop_table("conversation_states")
