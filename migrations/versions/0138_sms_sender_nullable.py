"""

Revision ID: 0138_sms_sender_nullable
Revises: 0137_notification_template_hist
Create Date: 2017-11-06 15:44:59.471977

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0138_sms_sender_nullable"
down_revision = "0137_notification_template_hist"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column("services", "sms_sender", existing_type=sa.VARCHAR(length=11), nullable=True)
    op.alter_column("services_history", "sms_sender", existing_type=sa.VARCHAR(length=11), nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column("services_history", "sms_sender", existing_type=sa.VARCHAR(length=11), nullable=False)
    op.alter_column("services", "sms_sender", existing_type=sa.VARCHAR(length=11), nullable=False)
    # ### end Alembic commands ###
