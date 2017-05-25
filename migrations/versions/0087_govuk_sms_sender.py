"""empty message

Revision ID: 0087_govuk_sms_sender
Revises: 0086_add_norm_to_notification
Create Date: 2017-05-22 13:46:09.584801

"""

# revision identifiers, used by Alembic.
revision = '0087_govuk_sms_sender'
down_revision = '0086_add_norm_to_notification'

from alembic import op


def upgrade():
    op.execute("UPDATE services SET sms_sender = 'GOVUK' where sms_sender is null")
    op.execute("UPDATE services_history SET sms_sender = 'GOVUK' where sms_sender is null")
    op.alter_column('services', 'sms_sender', nullable=False)
    op.alter_column('services_history', 'sms_sender', nullable=False)


def downgrade():
    op.alter_column('services_history', 'sms_sender', nullable=True)
    op.alter_column('services', 'sms_sender', nullable=True)
