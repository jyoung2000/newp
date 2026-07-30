"""user is_admin (head admin)

Revision ID: 7b2a4c9d1e50
Revises: 3c1f89b3bc03
Create Date: 2026-07-29 23:40:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = '7b2a4c9d1e50'
down_revision: str | None = '3c1f89b3bc03'
branch_labels = None
depends_on = None

# The seeded demo account. It is created non-interactively with a published
# password, so it must never be handed the admin role by a backfill.
DEMO_EMAIL = "demo@jobpilot.local"


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_admin',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    # Existing installs already have accounts, and nobody would be able to
    # reach user management without this: promote the earliest real account.
    # New installs have no users yet, so this is a no-op there and the first
    # registration takes the role instead (see api/auth.register).
    users = sa.table(
        'users',
        sa.column('id', sa.Integer),
        sa.column('email', sa.String),
        sa.column('is_admin', sa.Boolean),
    )
    bind = op.get_bind()
    first_id = bind.execute(
        sa.select(users.c.id)
        .where(users.c.email != DEMO_EMAIL)
        .order_by(users.c.id.asc())
        .limit(1)
    ).scalar()
    if first_id is not None:
        bind.execute(users.update().where(users.c.id == first_id).values(is_admin=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_admin')
