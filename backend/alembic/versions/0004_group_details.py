"""employment-history and reference group details

Revision ID: c4e81f70a9d2
Revises: 7b2a4c9d1e50
Create Date: 2026-07-30 03:10:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e81f70a9d2'
down_revision: str | None = '7b2a4c9d1e50'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('work_experiences', schema=None) as batch_op:
        batch_op.add_column(sa.Column('manager_name', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('manager_title', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('manager_email', sa.String(length=320), nullable=True))
        batch_op.add_column(sa.Column('manager_phone', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('may_contact_employer', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('reason_for_leaving', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('summary', sa.Text(), nullable=True))

    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('company', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('email', sa.String(length=320), nullable=True))
        batch_op.add_column(sa.Column('phone', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('years_known', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('reference_type', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('may_contact', sa.Boolean(), nullable=True))

    # `contact` was one box holding an email or a phone number. Split what is
    # already there rather than making people retype it: an '@' means email,
    # anything else is treated as a phone number. The original column is left
    # untouched, so nothing is lost if the guess is wrong.
    recs = sa.table(
        'recommendations',
        sa.column('id', sa.Integer),
        sa.column('contact', sa.String),
        sa.column('email', sa.String),
        sa.column('phone', sa.String),
    )
    bind = op.get_bind()
    bind.execute(
        recs.update()
        .where(recs.c.contact.isnot(None))
        .where(recs.c.contact.like('%@%'))
        .values(email=recs.c.contact)
    )
    bind.execute(
        recs.update()
        .where(recs.c.contact.isnot(None))
        .where(recs.c.contact.notlike('%@%'))
        .values(phone=recs.c.contact)
    )


def downgrade() -> None:
    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.drop_column('may_contact')
        batch_op.drop_column('reference_type')
        batch_op.drop_column('years_known')
        batch_op.drop_column('phone')
        batch_op.drop_column('email')
        batch_op.drop_column('company')

    with op.batch_alter_table('work_experiences', schema=None) as batch_op:
        batch_op.drop_column('summary')
        batch_op.drop_column('reason_for_leaving')
        batch_op.drop_column('may_contact_employer')
        batch_op.drop_column('manager_phone')
        batch_op.drop_column('manager_email')
        batch_op.drop_column('manager_title')
        batch_op.drop_column('manager_name')
