"""empty message

Revision ID: 0131_default_email_reply_to_row
Revises: 0130_service_email_reply_to_row
Create Date: 2017-08-29 14:09:41.042061

"""

# revision identifiers, used by Alembic.
revision = '0131_default_email_reply_to_row'
down_revision = '0130_service_email_reply_to_row'

from alembic import op


NOTIFY_SERVICE_ID = 'd6aa2c68-a2d9-4437-ab19-3ae8eb202553'
DEFAULT_EMAIL_REPLY_TO_ID = 'a13e4efe-5006-ce79-0ac3-c9cd8a7b3726'


def upgrade():
    op.execute("""
        INSERT INTO service_email_reply_to
        (id, service_id, email_address, is_default, created_at)
        VALUES
        ('{}','{}', 'notify@digital.cabinet-office.gov.uk', 't', NOW())
    """.format(DEFAULT_EMAIL_REPLY_TO_ID, NOTIFY_SERVICE_ID))


def downgrade():
    op.execute("""
        DELETE FROM service_email_reply_to
        WHERE id = '{}'
    """.format(DEFAULT_EMAIL_REPLY_TO_ID))
