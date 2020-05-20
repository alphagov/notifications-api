"""

Revision ID: 0321_update_postage_constraint_1
Revises: 0320_optimise_notifications
Create Date: 2020-05-12 16:17:21.874281

"""
import os

from alembic import op


revision = '0321_update_postage_constraint_1'
down_revision = '0320_optimise_notifications'
environment = os.environ['NOTIFY_ENVIRONMENT']


def upgrade():
    op.drop_constraint('chk_notifications_postage_null', 'notifications')
    op.execute("""
        ALTER TABLE notifications ADD CONSTRAINT "chk_notifications_postage_null"
        CHECK (
            CASE WHEN notification_type = 'letter' THEN
                postage is not null and postage in ('first', 'second', 'europe', 'rest-of-world')
            ELSE
                postage is null
            END
        )
        NOT VALID
    """)
    if environment not in ["live", "production"]:
        op.execute('ALTER TABLE notification_history DROP CONSTRAINT IF EXISTS chk_notification_history_postage_null')
    op.execute('COMMIT')


def downgrade():
    pass
    # To downgrade this migration and migrations 0322 and 0323 * LOCALLY ONLY * use the following code.
    # This should not be used in production - it will lock the tables for a long time
    #
    # op.drop_constraint('chk_notifications_postage_null', 'notifications')
    # op.drop_constraint('chk_templates_postage', 'templates')
    # op.drop_constraint('chk_templates_history_postage', 'templates_history')
    #
    # op.execute("""
    #     ALTER TABLE notifications ADD CONSTRAINT "chk_notifications_postage_null"
    #     CHECK (
    #         CASE WHEN notification_type = 'letter' THEN
    #             postage is not null and postage in ('first', 'second')
    #         ELSE
    #             postage is null
    #         END
    #     )
    # """)
    # op.execute("""
    #     ALTER TABLE notification_history ADD CONSTRAINT "chk_notification_history_postage_null"
    #     CHECK (
    #         CASE WHEN notification_type = 'letter' THEN
    #             postage is not null and postage in ('first', 'second')
    #         ELSE
    #             postage is null
    #         END
    #     )
    # """)
    # op.execute("""
    #     ALTER TABLE templates ADD CONSTRAINT "chk_templates_postage"
    #     CHECK (
    #         CASE WHEN template_type = 'letter' THEN
    #             postage is not null and postage in ('first', 'second')
    #         ELSE
    #             postage is null
    #         END
    #     )
    # """)
    # op.execute("""
    #     ALTER TABLE templates_history ADD CONSTRAINT "chk_templates_history_postage"
    #     CHECK (
    #         CASE WHEN template_type = 'letter' THEN
    #             postage is not null and postage in ('first', 'second')
    #         ELSE
    #             postage is null
    #         END
    #     )
    # """)
