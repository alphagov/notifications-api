"""
Create Date: 2026-07-31 09:47:18.388849
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0558_add_nhs_notify_org_type'
down_revision = '0557_create_ft_service_stats'


def upgrade():
    op.execute("INSERT INTO organisation_types (name, is_crown) VALUES ('nhs_notify', false)")


def downgrade():
    op.execute("UPDATE organisation SET organisation_type = 'nhs_central' WHERE organisation_type = 'nhs_notify'")
    op.execute("DELETE FROM organisation_types WHERE name = 'nhs_notify'")
