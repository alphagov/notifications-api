"""

Revision ID: 0121_nullable_logos
Revises: 0120_add_org_banner_branding
Create Date: 2017-09-20 11:00:20.415523

"""

import sqlalchemy as sa
from alembic import op

revision = "0121_nullable_logos"
down_revision = "0120_add_org_banner_branding"


def upgrade():
    op.alter_column("organisation", "logo", existing_type=sa.VARCHAR(length=255), nullable=True)


def downgrade():
    pass
