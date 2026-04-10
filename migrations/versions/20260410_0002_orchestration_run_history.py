"""add orchestration run history and dedupe fingerprints"""

from alembic import op
import sqlalchemy as sa

revision = "20260410_0002"
down_revision = "20260410_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("state_date", sa.Date(), nullable=True))
    op.add_column(
        "signals",
        sa.Column("fingerprint", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index("ix_signals_state_date", "signals", ["state_date"], unique=False)
    op.create_index("ix_signals_fingerprint", "signals", ["fingerprint"], unique=False)
    op.create_unique_constraint(
        "uq_signals_state_date_fingerprint",
        "signals",
        ["state_date", "fingerprint"],
    )

    op.add_column("alerts", sa.Column("state_date", sa.Date(), nullable=True))
    op.add_column(
        "alerts",
        sa.Column("fingerprint", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index("ix_alerts_state_date", "alerts", ["state_date"], unique=False)
    op.create_index("ix_alerts_fingerprint", "alerts", ["fingerprint"], unique=False)
    op.create_unique_constraint(
        "uq_alerts_state_date_fingerprint",
        "alerts",
        ["state_date", "fingerprint"],
    )

    op.create_table(
        "orchestration_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("state_date", sa.Date(), nullable=False),
        sa.Column("state_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_ids", sa.JSON(), nullable=False),
        sa.Column("alert_ids", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_orchestration_runs_state_date",
        "orchestration_runs",
        ["state_date"],
        unique=False,
    )
    op.create_index(
        "ix_orchestration_runs_executed_at",
        "orchestration_runs",
        ["executed_at"],
        unique=False,
    )
    op.create_index(
        "ix_orchestration_runs_state_fingerprint",
        "orchestration_runs",
        ["state_fingerprint"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_orchestration_runs_state_fingerprint", table_name="orchestration_runs")
    op.drop_index("ix_orchestration_runs_executed_at", table_name="orchestration_runs")
    op.drop_index("ix_orchestration_runs_state_date", table_name="orchestration_runs")
    op.drop_table("orchestration_runs")

    op.drop_constraint("uq_alerts_state_date_fingerprint", "alerts", type_="unique")
    op.drop_index("ix_alerts_fingerprint", table_name="alerts")
    op.drop_index("ix_alerts_state_date", table_name="alerts")
    op.drop_column("alerts", "fingerprint")
    op.drop_column("alerts", "state_date")

    op.drop_constraint("uq_signals_state_date_fingerprint", "signals", type_="unique")
    op.drop_index("ix_signals_fingerprint", table_name="signals")
    op.drop_index("ix_signals_state_date", table_name="signals")
    op.drop_column("signals", "fingerprint")
    op.drop_column("signals", "state_date")
