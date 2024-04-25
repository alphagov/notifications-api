"""

Revision ID: 0124_add_free_sms_fragment_limit
Revises: 0123_add_noti_to_email_reply
Create Date: 2017-10-10 11:30:16.225980

"""

import sqlalchemy as sa
from alembic import op

revision = "0124_add_free_sms_fragment_limit"
down_revision = "0123_add_noti_to_email_reply"


def upgrade():
    op.add_column("services_history", sa.Column("free_sms_fragment_limit", sa.BigInteger(), nullable=True))
    op.add_column("services", sa.Column("free_sms_fragment_limit", sa.BigInteger(), nullable=True))


def downgrade():
    op.drop_column("services_history", "free_sms_fragment_limit")
    op.drop_column("services", "free_sms_fragment_limit")
