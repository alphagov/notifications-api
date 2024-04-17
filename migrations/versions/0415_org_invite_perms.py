"""

Revision ID: 0415_org_invite_perms
Revises: 0414_org_user_permissions
Create Date: 2023-06-14 07:38:10.479332

"""

from alembic import op
import sqlalchemy as sa


revision = "0415_org_invite_perms"
down_revision = "0414_org_user_permissions"


def upgrade():
    op.add_column("invited_organisation_users", sa.Column("permissions", sa.String(), nullable=True))
    op.execute("UPDATE invited_organisation_users SET permissions = 'can_make_services_live'")
    op.alter_column("invited_organisation_users", "permissions", existing_nullable=True, nullable=False)


def downgrade():
    op.drop_column("invited_organisation_users", "permissions")
