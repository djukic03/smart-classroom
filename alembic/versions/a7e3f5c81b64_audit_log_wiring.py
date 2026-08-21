"""audit log wiring

Revision ID: a7e3f5c81b64
Revises: f2c48e91d3b7
Create Date: 2026-08-21 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7e3f5c81b64'
down_revision: str | Sequence[str] | None = 'f2c48e91d3b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ACTIONS = ('CREATE', 'UPDATE', 'DELETE', 'LOGIN', 'LOGOUT')


def upgrade() -> None:
    """Upgrade schema."""
    # Bez SET NULL brisanje korisnika puca cim audit zabelezi neki njegov
    # postupak -- strani kljuc bi drzao red i zabranio brisanje.
    op.drop_constraint('audit_logs_user_id_fkey', 'audit_logs', type_='foreignkey')
    op.create_foreign_key(
        'audit_logs_user_id_fkey',
        'audit_logs',
        'users',
        ['user_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # Atribucija mora da prezivi brisanje naloga.
    op.add_column('audit_logs', sa.Column('actor_email', sa.String(length=255), nullable=True))

    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'LOGIN_FAILED'")

    op.create_index(op.f('ix_audit_logs_timestamp'), 'audit_logs', ['timestamp'])


def downgrade() -> None:
    """Downgrade schema.

    PostgreSQL ne ume da ukloni vrednost iz enuma, pa se tip pravi ponovo.
    Redovi sa LOGIN_FAILED se pri tome brisu -- u staroj semi za njih nema
    mesta.
    """
    op.drop_index(op.f('ix_audit_logs_timestamp'), table_name='audit_logs')
    op.drop_column('audit_logs', 'actor_email')

    op.execute("DELETE FROM audit_logs WHERE action = 'LOGIN_FAILED'")
    values = ", ".join(f"'{value}'" for value in OLD_ACTIONS)
    op.execute(f"CREATE TYPE auditaction_old AS ENUM ({values})")
    op.execute(
        'ALTER TABLE audit_logs ALTER COLUMN action TYPE auditaction_old '
        'USING action::text::auditaction_old'
    )
    op.execute('DROP TYPE auditaction')
    op.execute('ALTER TYPE auditaction_old RENAME TO auditaction')

    op.drop_constraint('audit_logs_user_id_fkey', 'audit_logs', type_='foreignkey')
    op.create_foreign_key(
        'audit_logs_user_id_fkey', 'audit_logs', 'users', ['user_id'], ['id']
    )
