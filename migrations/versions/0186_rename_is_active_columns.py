"""

Revision ID: 0186_rename_is_active_columns
Revises: 0185_add_is_active_to_reply_tos
Create Date: 2018-04-27 16:35:41.824981

"""
from alembic import op
import sqlalchemy as sa


revision = '0186_rename_is_active_columns'
down_revision = '0185_add_is_active_to_reply_tos'


def upgrade():
    op.alter_column('service_email_reply_to', 'is_active', new_column_name='archived', server_default=sa.false())
    op.alter_column('service_letter_contacts', 'is_active', new_column_name='archived', server_default=sa.false())
    op.alter_column('service_sms_senders', 'is_active', new_column_name='archived', server_default=sa.false())

    op.execute("Update service_email_reply_to set archived = False")
    op.execute("Update service_letter_contacts set archived = False")
    op.execute("Update service_sms_senders set archived = False")


def downgrade():
    op.alter_column('service_email_reply_to', 'archived', new_column_name='is_active', server_default=sa.true())
    op.alter_column('service_letter_contacts', 'archived', new_column_name='is_active', server_default=sa.true())
    op.alter_column('service_sms_senders', 'archived', new_column_name='is_active', server_default=sa.true())

    op.execute("Update service_email_reply_to set is_active = True")
    op.execute("Update service_letter_contacts set is_active = True")
    op.execute("Update service_sms_senders set is_active = True")
