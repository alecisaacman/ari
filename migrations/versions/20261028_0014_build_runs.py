"""record what ARI's builder did with an approved build"""

import sqlalchemy as sa
from alembic import op

revision = "20261028_0014"
down_revision = "20261028_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("build_proposals", sa.Column("branch", sa.String(length=128), nullable=True))
    op.add_column("build_proposals", sa.Column("result", sa.Text(), nullable=True))
    op.add_column("build_proposals", sa.Column("built_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("build_proposals", sa.Column("announced_status", sa.String(length=32), nullable=True))


def downgrade() -> None:
    for column in ("announced_status", "built_at", "result", "branch"):
        op.drop_column("build_proposals", column)
