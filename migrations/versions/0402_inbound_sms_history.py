"""

Revision ID: 0402_inbound_sms_history
Revises: 0401_prefix_sms_non_null
Create Date: 2023-01-19 17:32:56.494917

"""

from alembic import op

revision = "0402_inbound_sms_history"
down_revision = "0401_prefix_sms_non_null"


def upgrade():
    op.create_index(op.f("ix_inbound_sms_history_created_at"), "inbound_sms_history", ["created_at"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_inbound_sms_history_created_at"), table_name="inbound_sms_history")
