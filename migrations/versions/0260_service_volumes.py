"""

Revision ID: 0260_service_volumes
Revises: 0259_remove_service_postage
Create Date: 2019-02-13 13:45:00.782500

"""
from alembic import op
from itertools import product
import sqlalchemy as sa


revision = '0260_service_volumes'
down_revision = '0259_remove_service_postage'


TABLES = ['services', 'services_history']
CHANNELS = ['volume_{}'.format(channel) for channel in ('email', 'letter', 'sms')]


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column('consent_to_research', sa.Boolean(), nullable=False, server_default=sa.false()))
        for channel in CHANNELS:
            op.add_column(table, sa.Column(channel, sa.Integer(), nullable=True))


def downgrade():
    for table in TABLES:
        op.drop_column(table, 'consent_to_research')
        for channel in CHANNELS:
            op.drop_column(table, channel)
