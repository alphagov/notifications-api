"""empty message

Revision ID: 0198_add_caseworking_permission
Revises: 0197_service_contact_link
Create Date: 2018-02-21 12:05:00

"""

# revision identifiers, used by Alembic.
revision = '0198_add_caseworking_permission'
down_revision = '0197_service_contact_link'

from alembic import op

PERMISSION_NAME = "caseworking"


def upgrade():
    op.get_bind()
    op.execute("insert into service_permission_types values('{}')".format(PERMISSION_NAME))


def downgrade():
    op.get_bind()
    op.execute("delete from service_permissions where permission = '{}'".format(PERMISSION_NAME))
    op.execute("delete from service_permission_types where name = '{}'".format(PERMISSION_NAME))
