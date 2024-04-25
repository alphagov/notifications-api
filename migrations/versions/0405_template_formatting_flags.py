"""

Revision ID: 0405_template_formatting_flags
Revises: 0404_remove_message_limit
Create Date: 2023-02-22 10:41:51.006163

"""

from alembic import op


revision = "0405_template_formatting_flags"
down_revision = "0404_remove_message_limit"


def upgrade():
    op.execute("INSERT INTO service_permission_types VALUES ('extra_email_formatting')")
    op.execute("INSERT INTO service_permission_types VALUES ('extra_letter_formatting')")


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'extra_email_formatting'")
    op.execute("DELETE FROM service_permissions WHERE permission = 'extra_letter_formatting'")

    op.execute("DELETE FROM service_permission_types WHERE name = 'extra_email_formatting'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'extra_letter_formatting'")
