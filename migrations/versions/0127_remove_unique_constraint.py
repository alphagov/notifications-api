"""

Revision ID: 0127_remove_unique_constraint
Revises: 0126_add_annual_billing
Create Date: 2017-10-17 16:47:37.826333

"""
import sqlalchemy as sa
from alembic import op

revision = "0127_remove_unique_constraint"
down_revision = "0126_add_annual_billing"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index("ix_service_sms_senders_service_id", table_name="service_sms_senders")
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_index("ix_service_sms_senders_service_id", "service_sms_senders", ["service_id"], unique=True)
    # ### end Alembic commands ###
