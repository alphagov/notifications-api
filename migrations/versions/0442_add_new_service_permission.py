"""

Revision ID: 0442_add_new_service_permission
Revises: 0441_add_unsubscribe_link
Create Date: 2024-04-05 16:50:27.631853

"""
from alembic import op


revision = "0442_add_new_service_permission"
down_revision = "0441_add_unsubscribe_link"


def upgrade():
    op.get_bind()
    op.execute("insert into service_permission_types values('sms_to_uk_landlines')")


def downgrade():
    op.get_bind()
    op.execute("delete from service_permissions where permission='sms_to_uk_landlines'")
    op.execute("delete from service_permission_types where name = 'sms_to_uk_landlines'")
