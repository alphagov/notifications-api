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


TABLES_AND_CHANNELS = product(
    ('services', 'services_history'),
    ('volume_{}'.format(channel) for channel in ('email', 'letter', 'sms')),
)


def upgrade():
    for table, channel in TABLES_AND_CHANNELS:
        op.add_column(table, sa.Column(channel, sa.Integer(), nullable=True))


def downgrade():
    for table, channel in TABLES_AND_CHANNELS:
        op.drop_column(table, channel)
