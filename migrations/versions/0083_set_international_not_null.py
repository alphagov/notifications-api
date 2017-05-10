"""empty message

Revision ID: 0083_set_international_not_null
Revises: 0082_set_international
Create Date: 2017-05-10 14:08:51.067762

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0083_set_international_not_null'
down_revision = '0082_set_international'


def upgrade():
    op.alter_column('notification_history', 'international',
                    existing_type=sa.BOOLEAN(),
                    nullable=False)
    op.alter_column('notifications', 'international',
                    existing_type=sa.BOOLEAN(),
                    nullable=False)


def downgrade():
    op.alter_column('notifications', 'international',
                    existing_type=sa.BOOLEAN(),
                    nullable=True)
    op.alter_column('notification_history', 'international',
                    existing_type=sa.BOOLEAN(),
                    nullable=True)
