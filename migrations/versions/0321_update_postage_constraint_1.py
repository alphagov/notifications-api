"""

Revision ID: 0321_update_postage_constraint_1
Revises: 0320_optimise_notifications
Create Date: 2020-03-11 12:01:41.533192

"""
from alembic import op
import sqlalchemy as sa


revision = '0321_update_postage_constraint_1'
down_revision = '0320_optimise_notifications'


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
    op.drop_constraint('chk_notification_history_postage_null', 'notification_history')


def downgrade():
    pass
    # To downgrade this migration and migrations 0320 and 0321 * LOCALLY ONLY * use the following code.
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
