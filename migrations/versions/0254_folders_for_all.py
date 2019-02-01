"""

Revision ID: 0254_folders_for_all
Revises: 0253_set_template_postage
Create Date: 2019-01-08 13:30:48.694881+00

"""
from alembic import op


revision = '0254_folders_for_all'
down_revision = '0253_set_template_postage'


def upgrade():
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
        permission='edit_folders'
    ))


def downgrade():
    pass
