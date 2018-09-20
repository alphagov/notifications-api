"""

Revision ID: 0228_notification_postage
Revises: 0227_postage_constraints
Create Date: 2018-09-19 11:42:52.229430

"""
from alembic import op
import sqlalchemy as sa


revision = '0228_notification_postage'
down_revision = '0227_postage_constraints'


def upgrade():
    op.add_column('notification_history', sa.Column('postage', sa.String(), nullable=True))
    op.add_column('notifications', sa.Column('postage', sa.String(), nullable=True))


def downgrade():
    op.drop_column('notifications', 'postage')
    op.drop_column('notification_history', 'postage')
