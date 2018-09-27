"""

Revision ID: 0230_noti_postage_constraint_3
Revises: 0230_noti_postage_constraint_2
Create Date: 2018-09-19 11:42:52.229430

"""
from alembic import op


revision = '0230_noti_postage_constraint_3'
down_revision = '0230_noti_postage_constraint_2'


def upgrade():
    op.execute('ALTER TABLE notifications VALIDATE CONSTRAINT "chk_notifications_postage_null"')
    op.execute('ALTER TABLE notification_history VALIDATE CONSTRAINT "chk_notification_history_postage_null"')


def downgrade():
    pass
