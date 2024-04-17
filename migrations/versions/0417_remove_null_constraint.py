"""

Revision ID: 0417_remove_null_constraint
Revises: 0416_add_org_user_perms
Create Date: 2023-06-21 12:45:27.185814

"""

from alembic import op


revision = "0417_remove_null_constraint"
down_revision = "0416_add_org_user_perms"


def upgrade():
    op.alter_column("invited_organisation_users", "permissions", existing_nullable=False, nullable=True)


def downgrade():
    op.alter_column("invited_organisation_users", "permissions", existing_nullable=True, nullable=False)
