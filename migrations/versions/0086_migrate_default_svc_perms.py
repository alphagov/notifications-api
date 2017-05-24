"""empty message

Revision ID: 0086_migrate_default_svc_perms
Revises: 0085_update_incoming_to_inbound
Create Date: 2017-05-23 18:13:03.532095

"""

# revision identifiers, used by Alembic.
revision = '0086_migrate_default_svc_perms'
down_revision = '0085_update_incoming_to_inbound'

from alembic import op
import sqlalchemy as sa


def upgrade():
    def get_values(permission):
        return "SELECT id, '{0}' FROM services WHERE "\
            "id NOT IN (SELECT service_id FROM service_permissions "\
            "WHERE service_id=id AND permission='{0}')".format(permission)

    op.execute("INSERT INTO service_permissions (service_id, permission) {}".format(get_values('sms')))
    op.execute("INSERT INTO service_permissions (service_id, permission) {}".format(get_values('email')))


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE created_at IS NULL")
