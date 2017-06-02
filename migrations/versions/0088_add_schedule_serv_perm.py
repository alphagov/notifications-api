"""empty message

Revision ID: 0088_add_schedule_serv_perm
Revises: 0087_scheduled_notifications
Create Date: 2017-05-26 14:53:18.581320

"""

# revision identifiers, used by Alembic.
revision = '0088_add_schedule_serv_perm'
down_revision = '0087_scheduled_notifications'

from alembic import op


def upgrade():
    op.get_bind()
    op.execute("insert into service_permission_types values('schedule_notifications')")


def downgrade():
    op.get_bind()
    op.execute("delete from service_permissions where permission = 'schedule_notifications'")
    op.execute("delete from service_permission_types where name = 'schedule_notifications'")
