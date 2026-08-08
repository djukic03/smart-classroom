"""measurements as timescaledb hypertable

Revision ID: a1c7f3e94b02
Revises: 138895d43617
Create Date: 2026-08-08 15:10:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c7f3e94b02'
down_revision: str | Sequence[str] | None = '138895d43617'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Ekstenzija se inace ukljucuje init skriptom, ali samo pri prvom kreiranju
    # klastera -- ovako migracija radi i na bazi napravljenoj naknadno.
    op.execute('CREATE EXTENSION IF NOT EXISTS timescaledb')

    # TimescaleDB ne dozvoljava jedinstveni indeks koji ne sadrzi kolonu po kojoj
    # se particionise, pa primarni kljuc mora da obuhvati i `timestamp`.
    op.drop_constraint('measurements_pkey', 'measurements', type_='primary')
    op.create_primary_key('measurements_pkey', 'measurements', ['id', 'timestamp'])

    op.execute(
        "SELECT create_hypertable('measurements', by_range('timestamp'), if_not_exists => TRUE)"
    )

    op.create_index(
        'ix_measurements_device_time', 'measurements', ['device_id', 'timestamp']
    )


def downgrade() -> None:
    """Downgrade schema.

    Hypertable se ne moze vratiti u obicnu tabelu, pa se tabela ponovo kreira.
    Postojeca merenja se pri tome gube.
    """
    op.drop_index('ix_measurements_device_time', table_name='measurements')
    op.execute('DROP TABLE measurements')
    op.create_table(
        'measurements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('co2', sa.Float(), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('humidity', sa.Float(), nullable=True),
        sa.Column('illuminance', sa.Float(), nullable=True),
        sa.Column('sound', sa.Float(), nullable=True),
        sa.Column('occupancy', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
