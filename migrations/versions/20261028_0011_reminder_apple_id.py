"""link ARI's reminders to the reminders it puts in Apple Reminders"""

import sqlalchemy as sa
from alembic import op

revision = "20261028_0011"
down_revision = "20261028_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reminders", sa.Column("apple_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("reminders", "apple_id")
