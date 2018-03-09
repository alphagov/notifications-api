"""

Revision ID: 0173_create_daily_sorted_letter
Revises: 0172_deprioritise_examples
Create Date: 2018-03-01 11:53:32.964256

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0173_create_daily_sorted_letter'
down_revision = '0172_deprioritise_examples'


def upgrade():
    op.create_table('daily_sorted_letter',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('billing_day', sa.Date(), nullable=False),
    sa.Column('unsorted_count', sa.Integer(), nullable=False),
    sa.Column('sorted_count', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_daily_sorted_letter_billing_day'), 'daily_sorted_letter', ['billing_day'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_daily_sorted_letter_billing_day'), table_name='daily_sorted_letter')
    op.drop_table('daily_sorted_letter')
