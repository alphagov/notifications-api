"""

Revision ID: 0185_add_is_active_to_reply_tos
Revises: 0184_alter_primary_key_1
Create Date: 2018-04-10 16:35:41.824981

"""
from alembic import op
import sqlalchemy as sa


revision = '0185_add_is_active_to_reply_tos'
down_revision = '0184_alter_primary_key_1'


def upgrade():
    op.add_column('service_email_reply_to', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('service_letter_contacts', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('service_sms_senders', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column('service_sms_senders', 'is_active')
    op.drop_column('service_letter_contacts', 'is_active')
    op.drop_column('service_email_reply_to', 'is_active')
