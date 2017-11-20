"""

Revision ID: 0140_sms_prefix_non_nullable
Revises: 0139_migrate_sms_allowance_data
Create Date: 2017-11-07 13:04:04.077142

"""
from alembic import op
from flask import current_app
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0140_sms_prefix_non_nullable'
down_revision = '0139_migrate_sms_allowance_data'


def upgrade():

    op.execute("""
        update services
        set prefix_sms = false
        where id = '{}'
    """.format(current_app.config['NOTIFY_SERVICE_ID']))

    op.alter_column(
        'services',
        'prefix_sms',
        existing_type=sa.BOOLEAN(),
        nullable=False,
    )


def downgrade():

    op.alter_column(
        'services',
        'prefix_sms',
        existing_type=sa.BOOLEAN(),
        nullable=True,
    )

    op.execute("""
        update services
        set prefix_sms = null
        where id = '{}'
    """.format(current_app.config['NOTIFY_SERVICE_ID']))
