"""

Revision ID: 0194_ft_billing_created_at
Revises: 0193_add_ft_billing_timestamps
Create Date: 2018-05-22 14:34:27.852096

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0194_ft_billing_created_at'
down_revision = '0193_add_ft_billing_timestamps'


def upgrade():
    op.execute("UPDATE ft_billing SET created_at = NOW()")
    op.alter_column('ft_billing', 'created_at', nullable=False)


def downgrade():
    op.alter_column('ft_billing', 'created_at', nullable=True)
    op.execute("UPDATE ft_billing SET created_at = null")
