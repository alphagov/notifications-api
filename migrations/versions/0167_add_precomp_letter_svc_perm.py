"""empty message

Revision ID: 0167_add_precomp_letter_svc_perm
Revises: 0166_add_org_user_stuff
Create Date: 2018-02-21 12:05:00

"""

# revision identifiers, used by Alembic.
revision = '0167_add_precomp_letter_svc_perm'
down_revision = '0166_add_org_user_stuff'

from alembic import op


def upgrade():
    op.get_bind()
    op.execute("insert into service_permission_types values('precompiled_letter')")


def downgrade():
    op.get_bind()
    op.execute("delete from service_permissions where permission = 'precompiled_letter'")
    op.execute("delete from service_permission_types where name = 'precompiled_letter'")
