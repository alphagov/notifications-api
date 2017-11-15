"""

Revision ID: 0137_notification_template_hist
Revises: 0136_user_mobile_nullable
Create Date: 2017-11-08 10:15:07.039227

"""
from alembic import op

revision = '0137_notification_template_hist'
down_revision = '0136_user_mobile_nullable'


def upgrade():
    op.drop_constraint('notifications_template_id_fkey', 'notifications', type_='foreignkey')
    op.execute("""
        ALTER TABLE notifications ADD CONSTRAINT "notifications_templates_history_fkey"
        FOREIGN KEY ("template_id", "template_version") REFERENCES "templates_history" ("id", "version")
        NOT VALID
    """)

    op.drop_constraint('notification_history_template_id_fkey', 'notification_history', type_='foreignkey')
    op.execute("""
        ALTER TABLE notification_history ADD CONSTRAINT "notification_history_templates_history_fkey"
        FOREIGN KEY ("template_id", "template_version") REFERENCES "templates_history" ("id", "version")
        NOT VALID
    """)


def downgrade():
    op.drop_constraint('notifications_templates_history_fkey', 'notifications', type_='foreignkey')
    op.create_foreign_key('notifications_template_id_fkey', 'notifications', 'templates', ['template_id'], ['id'])

    op.drop_constraint('notification_history_templates_history_fkey', 'notification_history', type_='foreignkey')
    op.create_foreign_key('notification_history_template_id_fkey', 'notification_history', 'templates',
                          ['template_id'], ['id'])
