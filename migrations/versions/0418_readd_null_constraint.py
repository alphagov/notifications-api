"""

Revision ID: 0418_readd_null_constraint
Revises: 0417_remove_null_constraint
Create Date: 2023-06-21 13:40:37.866124

"""

from alembic import op


revision = "0418_readd_null_constraint"
down_revision = "0417_remove_null_constraint"


def upgrade():
    op.execute("UPDATE invited_organisation_users SET permissions = '' WHERE permissions IS NULL")
    op.alter_column("invited_organisation_users", "permissions", existing_nullable=True, nullable=False)


def downgrade():
    op.alter_column("invited_organisation_users", "permissions", existing_nullable=False, nullable=True)
