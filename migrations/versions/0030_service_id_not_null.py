"""empty message

Revision ID: 0030_service_id_not_null
Revises: 0029_fix_email_from
Create Date: 2016-06-15 15:51:41.355149

"""

# revision identifiers, used by Alembic.

from sqlalchemy.dialects import postgresql

revision = '0030_service_id_not_null'
down_revision = '0029_fix_email_from'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column('permissions', 'service_id',
               existing_type=postgresql.UUID(),
               nullable=True)


def downgrade():
    op.alter_column('permissions', 'service_id',
               existing_type=postgresql.UUID(),
               nullable=False)