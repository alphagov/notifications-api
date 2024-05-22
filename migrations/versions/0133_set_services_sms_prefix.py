import os

from app import config

"""

Revision ID: 0133_set_services_sms_prefix
Revises: 0132_add_sms_prefix_setting
Create Date: 2017-11-03 15:55:35.657488

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0133_set_services_sms_prefix"
down_revision = "0132_add_sms_prefix_setting"

notify_environment = os.environ["NOTIFY_ENVIRONMENT"]
if notify_environment in config.configs:
    config = config.configs[notify_environment]
else:
    config = config.Config()

default_sms_sender = config.FROM_NUMBER


def upgrade():
    op.execute(
        """
        update services set prefix_sms = True
        where id in (
            select service_id from service_sms_senders
            where is_default = True and sms_sender = '{}'
        )
    """.format(
            default_sms_sender
        )
    )
    op.execute(
        """
        update services set prefix_sms = False
        where id in (
            select service_id from service_sms_senders
            where is_default = True and sms_sender != '{}'
        )
    """.format(
            default_sms_sender
        )
    )


def downgrade():
    op.execute(
        """
        UPDATE services set prefix_sms = null
    """
    )
