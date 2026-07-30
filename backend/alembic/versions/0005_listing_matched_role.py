"""listing matched_role

Revision ID: e9a71c3d4b60
Revises: c4e81f70a9d2
Create Date: 2026-07-30 05:50:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = 'e9a71c3d4b60'
down_revision: str | None = 'c4e81f70a9d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('job_listings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('matched_role', sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('job_listings', schema=None) as batch_op:
        batch_op.drop_column('matched_role')
