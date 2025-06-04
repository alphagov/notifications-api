"""
Create Date: 2025-06-03 12:07:37.877855
"""

from alembic import op

revision = '0503_remove_old_permissions'
down_revision = '0502_add_confirmed_unique'


def upgrade():
    op.execute("DELETE from service_permissions where permission in ('schedule_notifications', 'letters_as_pdf'," \
    "'precompiled_letter', 'upload_document', 'extra_email_formatting', 'extra_letter_formatting', 'economy_letter_sending')")
    op.execute("DELETE from service_permission_types where name in ('schedule_notifications', 'letters_as_pdf'," \
    "'precompiled_letter', 'upload_document', 'extra_email_formatting', 'extra_letter_formatting', 'economy_letter_sending')")


def downgrade():
    op.execute("INSERT INTO service_permission_types values ('schedule_notifications'), ('letters_as_pdf')," \
    "('precompiled_letter'), ('upload_document'), ('extra_email_formatting'), ('extra_letter_formatting'), ('economy_letter_sending')")
