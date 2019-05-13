"""

Revision ID: 0289_precompiled_for_all
Revises: 0288_add_go_live_user
Create Date: 2019-05-13 10:44:51.867661

"""
from alembic import op


revision = '0289_precompiled_for_all'
down_revision = '0288_add_go_live_user'


def upgrade():
    op.execute("DELETE from service_permissions where permission = 'precompiled_letter'")
    op.execute("DELETE from service_permission_types where name = 'precompiled_letter'")


def downgrade():
    op.execute("INSERT INTO service_permission_types values('precompiled_letter')")
    op.execute("""
           INSERT INTO
               service_permissions (service_id, permission, created_at)
           SELECT
               id, '{permission}', now()
           FROM
               services
           WHERE
               NOT EXISTS (
                   SELECT
                   FROM
                       service_permissions
                   WHERE
                       service_id = services.id and
                       permission = '{permission}'
               )
       """.format(
        permission='precompiled_letter'
    ))
