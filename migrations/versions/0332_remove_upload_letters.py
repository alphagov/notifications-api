"""

Revision ID: 0332_remove_upload_letters_permission
Revises: 0331_add_broadcast_org
Create Date: 2020-09-23 10:11:01.094412

"""
from alembic import op

revision = '0332_remove_upload_letters'
down_revision = '0331_add_broadcast_org'

PERMISSION = 'upload_letters'


def upgrade():
    op.execute(f"""
        DELETE
            FROM service_permissions
        WHERE
            permission = '{PERMISSION}'
        ;
    """)
    op.execute(f"""
        DELETE
            FROM service_permission_types
        WHERE
            name = '{PERMISSION}'
        ;
    """)


def downgrade():
    pass
