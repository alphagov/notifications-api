"""

Revision ID: 4561e334fa59
Revises: 0357_validate_constraint
Create Date: 2021-05-25 10:43:33.880337

"""
from alembic import op
import sqlalchemy as sa


revision = '4561e334fa59'
down_revision = '0357_validate_constraint'


def upgrade():
    op.create_check_constraint(
        "op_users_webauthn_or_not_platform_admin",
        "users",
        "(auth_type = 'webauthn_auth') OR (platform_admin = false)"
    )


def downgrade():
    op.drop_constraint(
        "op_users_webauthn_or_not_platform_admin",
        "users",
    )
