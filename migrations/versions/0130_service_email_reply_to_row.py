"""empty message

Revision ID: 0130_service_email_reply_to_row
Revises: 0129_add_email_auth_permission
Create Date: 2017-08-29 14:09:41.042061

"""

# revision identifiers, used by Alembic.
revision = '0130_service_email_reply_to_row'
down_revision = '0129_add_email_auth_permission'

from alembic import op


NOTIFY_SERVICE_ID = 'd6aa2c68-a2d9-4437-ab19-3ae8eb202553'
EMAIL_REPLY_TO_ID = 'b3a58d57-2337-662a-4cba-40792a9322f2'


def upgrade():
    op.execute("""
        INSERT INTO service_email_reply_to
        (id, service_id, email_address, is_default, created_at)
        VALUES
        ('{}','{}', 'notify+1@digital.cabinet-office.gov.uk', 'f', NOW())
    """.format(EMAIL_REPLY_TO_ID, NOTIFY_SERVICE_ID))


def downgrade():
    op.execute("""
        DELETE FROM service_email_reply_to
        WHERE id = '{}'
    """.format(EMAIL_REPLY_TO_ID))
