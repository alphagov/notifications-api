"""

Revision ID: 0317_uploads_for_all
Revises: 0316_int_letters_permission
Create Date: 2019-05-13 10:44:51.867661

"""
from alembic import op
from app.models import UPLOAD_LETTERS


revision = '0317_uploads_for_all'
down_revision = '0316_int_letters_permission'


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
        permission=UPLOAD_LETTERS
    ))


def downgrade():
    op.execute("DELETE from service_permissions where permission = '{}'".format(
        UPLOAD_LETTERS
    ))
