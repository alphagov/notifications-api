"""
Create Date: 2025-01-17 12:30:50.050539
"""

from alembic import op

revision = '0847_insert_new_callback_types'
down_revision = '0486_letter_rates_feb_2025'


def upgrade():
    insert_returned_letter_callback_type = "INSERT INTO service_callback_type VALUES ('returned_letters')"
    insert_inbound_sms_callback_type = "INSERT INTO service_callback_type VALUES ('inbound_sms')"
    op.execute(insert_returned_letter_callback_type)
    op.execute(insert_inbound_sms_callback_type)


def downgrade():
    pass
