"""
Create Date: 2025-01-16 11:15:04.021579
"""

from alembic import op


revision = "0486_insert_returned_letter"
down_revision = "0485_add_job_status_fin_allrws"


def upgrade():
    insert_returned_letter_callback_type = "INSERT INTO service_callback_type VALUES ('returned_letters')"
    insert_inbound_sms_callback_type = "INSERT INTO service_callback_type VALUES ('inbound_sms')"
    op.execute(insert_returned_letter_callback_type)
    op.execute(insert_inbound_sms_callback_type)


def downgrade():
    delete_returned_letter_callback_type = "DELETE FROM service_callback_type WHERE name = 'returned_letters'"
    delete_inbound_sms_callback_type = "DELETE FROM service_callback_type WHERE name = 'inbound_sms'"
    op.execute(delete_returned_letter_callback_type)
    op.execute(delete_inbound_sms_callback_type)
