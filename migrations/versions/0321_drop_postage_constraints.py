"""

Revision ID: 0321_drop_postage_constraints
Revises: 0320_optimise_notifications
Create Date: 2020-06-08 11:48:53.315768

"""
import os

from alembic import op


revision = '0321_drop_postage_constraints'
down_revision = '0320_optimise_notifications'
environment = os.environ['NOTIFY_ENVIRONMENT']


def upgrade():
    if environment not in ["live", "production"]:
        op.execute('ALTER TABLE notifications DROP CONSTRAINT IF EXISTS chk_notifications_postage_null')
        op.execute('ALTER TABLE notification_history DROP CONSTRAINT IF EXISTS chk_notification_history_postage_null')

    op.execute('ALTER TABLE templates DROP CONSTRAINT IF EXISTS chk_templates_postage')
    op.execute('ALTER TABLE templates_history DROP CONSTRAINT IF EXISTS chk_templates_history_postage')


def downgrade():
    # The downgrade command must not be run in production - it will lock the tables for a long time
    if environment not in ["live", "production"]:
        op.execute("""
            ALTER TABLE notifications ADD CONSTRAINT "chk_notifications_postage_null"
            CHECK (
                CASE WHEN notification_type = 'letter' THEN
                    postage is not null and postage in ('first', 'second')
                ELSE
                    postage is null
                END
            )
        """)
        op.execute("""
            ALTER TABLE notification_history ADD CONSTRAINT "chk_notification_history_postage_null"
            CHECK (
                CASE WHEN notification_type = 'letter' THEN
                    postage is not null and postage in ('first', 'second')
                ELSE
                    postage is null
                END
            )
        """)
        op.execute("""
            ALTER TABLE templates ADD CONSTRAINT "chk_templates_postage"
            CHECK (
                CASE WHEN template_type = 'letter' THEN
                    postage is not null and postage in ('first', 'second')
                ELSE
                    postage is null
                END
            )
        """)
        op.execute("""
            ALTER TABLE templates_history ADD CONSTRAINT "chk_templates_history_postage"
            CHECK (
                CASE WHEN template_type = 'letter' THEN
                    postage is not null and postage in ('first', 'second')
                ELSE
                    postage is null
                END
            )
        """)
