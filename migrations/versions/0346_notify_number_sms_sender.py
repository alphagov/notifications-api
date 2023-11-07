"""

Revision ID: 0346_notify_number_sms_sender
Revises: 0345_move_broadcast_provider
Create Date: 2021-02-17 10:40:10.181087

"""
import uuid

from alembic import op
from flask import current_app

revision = "0346_notify_number_sms_sender"
down_revision = "0345_move_broadcast_provider"

SMS_SENDER_ID = "d24b830b-57b4-4f14-bd80-02f46f8d54de"
NOTIFY_SERVICE_ID = current_app.config["NOTIFY_SERVICE_ID"]
INBOUND_NUMBER = current_app.config["NOTIFY_INTERNATIONAL_SMS_SENDER"]


def upgrade():
    sql = f"""INSERT INTO service_sms_senders (id, sms_sender, service_id, is_default, created_at)
            VALUES ('{SMS_SENDER_ID}', '{INBOUND_NUMBER}', '{NOTIFY_SERVICE_ID}',false, now())"""

    op.execute(sql)
    inbound_number_id = uuid.uuid4()
    # by adding a row in inbound_number we ensure the number isn't added to the table and assigned to a service.
    inbound_number_sql = f"""INSERT INTO INBOUND_NUMBERS (id, number, provider, active, created_at)
            VALUES('{inbound_number_id}', '{INBOUND_NUMBER}', 'mmg', false, now())
    """
    op.execute(inbound_number_sql)


def downgrade():
    delete_sms_sender = f"delete from service_sms_senders where id = '{SMS_SENDER_ID}'"
    delete_inbound_number = f"delete from inbound_numbers where number = '{INBOUND_NUMBER}'"
    op.execute(delete_sms_sender)
    op.execute(delete_inbound_number)
