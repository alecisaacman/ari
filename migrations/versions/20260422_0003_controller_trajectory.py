"""add controller trajectory to orchestration runs"""

from alembic import op
import sqlalchemy as sa

revision = "20260422_0003"
down_revision = "20260410_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orchestration_runs",
        sa.Column("controller_trajectory", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orchestration_runs", "controller_trajectory")
