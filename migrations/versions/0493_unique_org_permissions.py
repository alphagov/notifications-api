"""
Create Date: 2025-04-04 16:37:49.511033
"""

from alembic import op

revision = '0493_unique_org_permissions'
down_revision = '0492_sms_rate_april_2025'


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("CREATE UNIQUE INDEX CONCURRENTLY uix_organisation_permission ON organisation_permissions (organisation_id, permission)")
        op.execute("ALTER TABLE organisation_permissions ADD CONSTRAINT uix_organisation_permission UNIQUE USING INDEX uix_organisation_permission")

def downgrade():
    op.drop_constraint('uix_organisation_permission', 'organisation_permissions', type_='unique')
