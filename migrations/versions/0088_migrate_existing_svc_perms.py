"""empty message

Revision ID: 0088_migrate_existing_svc_perms
Revises: 0087_scheduled_notifications
Create Date: 2017-05-23 18:13:03.532095

"""

# revision identifiers, used by Alembic.
revision = '0088_migrate_existing_svc_perms'
down_revision = '0087_scheduled_notifications'

from alembic import op
import sqlalchemy as sa
import time

migration_date = time.strftime('2017-05-26 17:30:00.000000')


def upgrade():
    def get_values(permission):
        return "SELECT id, '{0}', '{1}' FROM services WHERE "\
            "id NOT IN (SELECT service_id FROM service_permissions "\
            "WHERE service_id=id AND permission='{0}')".format(permission, migration_date)

    def get_values_if_flag(permission, flag):
        return "SELECT id, '{0}', '{1}' FROM services WHERE "\
            "{2} AND id NOT IN (SELECT service_id FROM service_permissions "\
            "WHERE service_id=id AND permission='{0}')".format(permission, migration_date, flag)

    op.execute("INSERT INTO service_permissions (service_id, permission, created_at) {}".format(get_values('sms')))
    op.execute("INSERT INTO service_permissions (service_id, permission, created_at) {}".format(get_values('email')))
    op.execute("INSERT INTO service_permissions (service_id, permission, created_at) {}".format(
        get_values_if_flag('letter', 'can_send_letters')))
    op.execute("INSERT INTO service_permissions (service_id, permission, created_at) {}".format(
        get_values_if_flag('international_sms', 'can_send_international_sms')))


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE created_at = '{}'::timestamp".format(migration_date))
