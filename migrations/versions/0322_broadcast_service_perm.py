"""

Revision ID: 0322_broadcast_service_perm
Revises: 0321_drop_postage_constraints
Create Date: 2020-06-29 11:14:13.183683

"""
from alembic import op


revision = '0322_broadcast_service_perm'
down_revision = '0321_drop_postage_constraints'


def upgrade():
    op.execute("INSERT INTO service_permission_types VALUES ('broadcast')")


def downgrade():
    op.execute("DELETE FROM service_permissions WHERE permission = 'broadcast'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'broadcast'")
