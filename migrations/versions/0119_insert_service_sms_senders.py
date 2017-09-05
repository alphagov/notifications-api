"""empty message

Revision ID: 0119_insert_service_sms_senders
Revises: 0118_service_sms_senders
Create Date: 2017-09-05 17:21:14.816199

"""
import uuid

from alembic import op

revision = '0119_insert_service_sms_senders'
down_revision = '0118_service_sms_senders'


def upgrade():
    query = """SELECT id, number, service_id
               FROM inbound_numbers
               WHERE service_id is not null"""

    conn = op.get_bind()
    results = conn.execute(query)
    res = results.fetchall()

    for x in res:
        op.execute(
            """
            INSERT INTO service_sms_senders
            (
                id,
                sms_sender,
                service_id,
                inbound_number_id,
                is_default,
                created_at
            )
            VALUES
            (
                '{}',
                '{}',
                '{}',
                '{}',
                True,
                now()
            )
            """.format(uuid.uuid4(), x.number, x.service_id, x.id)
        )


def downgrade():
    op.execute(
        """
        DELETE FROM service_sms_senders
        """
    )
