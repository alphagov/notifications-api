"""

Revision ID: 0189_ft_billing_data_type
Revises: 0188_add_ft_notification_status
Create Date: 2018-05-10 14:57:52.589773

"""
from alembic import op
import sqlalchemy as sa

revision = '0189_ft_billing_data_type'
down_revision = '0188_add_ft_notification_status'


def upgrade():
    op.alter_column('ft_billing', 'billable_units',
                    existing_type=sa.NUMERIC(),
                    type_=sa.Integer(),
                    existing_nullable=True)
    op.alter_column('ft_billing', 'rate_multiplier',
                    existing_type=sa.NUMERIC(),
                    type_=sa.Integer())


def downgrade():
    op.alter_column('ft_billing', 'rate_multiplier',
                    existing_type=sa.Integer(),
                    type_=sa.NUMERIC())
    op.alter_column('ft_billing', 'billable_units',
                    existing_type=sa.Integer(),
                    type_=sa.NUMERIC(),
                    existing_nullable=True)
