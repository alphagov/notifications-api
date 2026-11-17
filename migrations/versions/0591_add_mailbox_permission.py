"""

Revision ID: 0591_add_mailbox_permission
Revises: 0590_add_mailbox_template_type
Create Date: 2026-11-16 12:14:26

"""

from alembic import op


revision = "0591_add_mailbox_permission"
down_revision = "0590_add_mailbox_template_type"


def upgrade():
    op.get_bind()
    op.execute("insert into service_permission_types values('mailbox')")


def downgrade():
    op.get_bind()
    op.execute("delete from service_permissions where permission='mailbox'")
    op.execute("delete from service_permission_types where name = 'mailbox'")
