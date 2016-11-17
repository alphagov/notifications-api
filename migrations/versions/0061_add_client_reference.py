"""empty message

Revision ID: 0061_add_client_reference
Revises: 0060_add_letter_template_type
Create Date: 2016-11-17 13:19:25.820617

"""

# revision identifiers, used by Alembic.
revision = '0061_add_client_reference'
down_revision = '0060_add_letter_template_type'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('notifications', sa.Column('client_reference', sa.String(), index=True, nullable=True))
    op.add_column('notification_history', sa.Column('client_reference', sa.String(), nullable=True))


def downgrade():
    op.drop_column('notifications', 'client_reference')
    op.drop_column('notification_history', 'client_reference')
