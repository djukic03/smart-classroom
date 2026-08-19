"""per sensor schedules

Revision ID: e5b93d17a204
Revises: d8f1a3c92b47
Create Date: 2026-08-18 15:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5b93d17a204'
down_revision: str | Sequence[str] | None = 'd8f1a3c92b47'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Raspored prelazi sa uredjaja na pojedinacni senzor. Tabela `schedules` je
    prazna i nijedan kod je nije koristio, pa se umesto niza ALTER-a ponovo
    kreira -- nema podataka koje bi trebalo preseliti.
    """
    op.add_column(
        'sensor_configs',
        sa.Column('on_schedule', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('sensor_configs', 'on_schedule', server_default=None)

    op.drop_column('device_configs', 'on_schedule')

    op.drop_table('schedules')
    op.create_table(
        'schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sensor_config_id', sa.Integer(), nullable=False),
        sa.Column('day_of_week', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.CheckConstraint('day_of_week BETWEEN 0 AND 6', name='ck_schedule_day'),
        sa.CheckConstraint('start_time < end_time', name='ck_schedule_time_order'),
        sa.ForeignKeyConstraint(['sensor_config_id'], ['sensor_configs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'sensor_config_id', 'day_of_week', 'start_time', 'end_time',
            name='uq_schedule_window',
        ),
    )
    op.create_index(
        op.f('ix_schedules_sensor_config_id'), 'schedules', ['sensor_config_id']
    )


def downgrade() -> None:
    """Downgrade schema.

    Postojeci rasporedi se gube -- vezani su za senzor, a stara sema ih vezuje
    za uredjaj.
    """
    op.drop_index(op.f('ix_schedules_sensor_config_id'), table_name='schedules')
    op.drop_table('schedules')
    op.create_table(
        'schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_config_id', sa.Integer(), nullable=False),
        sa.Column('day_of_week', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(['device_config_id'], ['device_configs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.add_column(
        'device_configs',
        sa.Column('on_schedule', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('device_configs', 'on_schedule', server_default=None)

    op.drop_column('sensor_configs', 'on_schedule')
