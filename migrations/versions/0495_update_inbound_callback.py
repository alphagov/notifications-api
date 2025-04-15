"""
Create Date: 2025-04-07 14:22:20.057922
"""

from alembic import op

revision = '0495_update_inbound_callback'
down_revision = '0494_add_intl_sms_limit_column'


def upgrade():
    insert_inbound_sms_callback_type = "INSERT INTO service_callback_type VALUES ('inbound_sms')"
    op.execute(insert_inbound_sms_callback_type)


def downgrade():
    delete_inbound_sms_callback = "DELETE FROM service_callback_api WHERE callback_type='inbound_sms'"
    delete_inbound_sms_callback_history = \
        "DELETE FROM service_callback_api_history WHERE callback_type='inbound_sms'"
    delete_inbound_sms_callback_type = "DELETE FROM service_callback_type WHERE name='inbound_sms'"

    op.execute(delete_inbound_sms_callback)
    op.execute(delete_inbound_sms_callback_history)
    op.execute(delete_inbound_sms_callback_type)
