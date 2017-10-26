"""

Revision ID: 0129_add_email_auth_permission
Revises: 0128_noti_to_sms_sender
Create Date: 2017-10-26 14:33:41.336861

"""
from alembic import op


revision = '0129_add_email_auth_permission'
down_revision = '0128_noti_to_sms_sender'


def upgrade():
    op.execute("INSERT INTO service_permission_types VALUES ('email_auth')")


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'email_auth'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'email_auth'")
