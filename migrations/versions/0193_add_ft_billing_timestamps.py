"""

Revision ID: 0193_add_ft_billing_timestamps
Revises: 0192_drop_provider_statistics
Create Date: 2018-05-22 10:23:21.937262

"""
from alembic import op
import sqlalchemy as sa


revision = '0193_add_ft_billing_timestamps'
down_revision = '0192_drop_provider_statistics'


def upgrade():
    op.add_column('ft_billing', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.add_column('ft_billing', sa.Column('created_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('ft_billing', 'created_at')
    op.drop_column('ft_billing', 'updated_at')
