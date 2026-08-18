"""device config version

Revision ID: c4a2b8e17f30
Revises: b7d41c05e832
Create Date: 2026-08-17 13:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4a2b8e17f30'
down_revision: str | Sequence[str] | None = 'b7d41c05e832'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default popunjava postojece redove, pa se odmah uklanja kako bi se
    # sema poklapala sa modelom (podrazumevanu vrednost postavlja ORM).
    op.add_column(
        'device_configs',
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
    )
    op.alter_column('device_configs', 'version', server_default=None)

    op.add_column(
        'device_configs',
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.alter_column('device_configs', 'updated_at', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('device_configs', 'updated_at')
    op.drop_column('device_configs', 'version')
