"""hourly measurement aggregate

Revision ID: b7d41c05e832
Revises: 4309ee2416d9
Create Date: 2026-08-12 15:20:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = 'b7d41c05e832'
down_revision: str | Sequence[str] | None = '4309ee2416d9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEW = "measurements_hourly"

METRICS = ("co2", "temperature", "humidity", "illuminance", "sound", "occupancy")


def _metric_columns() -> str:
    parts = []
    for metric in METRICS:
        parts.append(f"sum({metric}) AS {metric}_sum")
        parts.append(f"count({metric}) AS {metric}_count")
        parts.append(f"min({metric}) AS {metric}_min")
        parts.append(f"max({metric}) AS {metric}_max")
    return ",\n           ".join(parts)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        f"""
        CREATE MATERIALIZED VIEW {VIEW}
        WITH (timescaledb.continuous) AS
        SELECT device_id,
               time_bucket('1 hour', timestamp) AS bucket,
               count(*) AS samples,
               {_metric_columns()}
        FROM measurements
        GROUP BY device_id, bucket
        WITH NO DATA
        """
    )

    op.execute(
        f"ALTER MATERIALIZED VIEW {VIEW} SET (timescaledb.materialized_only = false)"
    )

    op.execute(
        f"""
        SELECT add_continuous_aggregate_policy(
            '{VIEW}',
            start_offset => INTERVAL '30 days',
            end_offset => INTERVAL '1 hour',
            schedule_interval => INTERVAL '30 minutes'
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {VIEW}")
