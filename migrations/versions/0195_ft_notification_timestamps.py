"""

Revision ID: 0195_ft_notification_timestamps
Revises: 0194_ft_billing_created_at
Create Date: 2018-05-22 16:01:53.269137

"""
from alembic import op
import sqlalchemy as sa


revision = '0195_ft_notification_timestamps'
down_revision = '0194_ft_billing_created_at'


def upgrade():
    op.add_column('ft_notification_status', sa.Column('created_at', sa.DateTime(), nullable=False))
    op.add_column('ft_notification_status', sa.Column('updated_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('ft_notification_status', 'updated_at')
    op.drop_column('ft_notification_status', 'created_at')
