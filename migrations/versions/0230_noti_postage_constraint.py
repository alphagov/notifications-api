"""

Revision ID: 0230_noti_postage_constraint
Revises: 0229_new_letter_rates
Create Date: 2018-09-19 11:42:52.229430

"""
from alembic import op


revision = '0230_noti_postage_constraint'
down_revision = '0229_new_letter_rates'


def upgrade():
    op.execute("""
        ALTER TABLE notifications ADD CONSTRAINT "chk_notifications_postage_null"
        CHECK (
            CASE WHEN notification_type = 'letter' THEN
                postage in ('first', 'second')
            ELSE
                postage is null
            END
        )
        NOT VALID
    """)
    op.execute("""
        ALTER TABLE notification_history ADD CONSTRAINT "chk_notification_history_postage_null"
        CHECK (
            CASE WHEN notification_type = 'letter' THEN
                postage in ('first', 'second')
            ELSE
                postage is null
            END
        )
        NOT VALID
    """)
    op.execute('ALTER TABLE notifications VALIDATE CONSTRAINT "chk_notifications_postage_null"')
    op.execute('ALTER TABLE notification_history VALIDATE CONSTRAINT "chk_notification_history_postage_null"')


def downgrade():
    op.drop_constraint('chk_notifications_postage_null', 'notifications', type_='check')
    op.drop_constraint('chk_notification_history_postage_null', 'notification_history', type_='check')
