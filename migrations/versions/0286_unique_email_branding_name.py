"""

Revision ID: 0286_unique_email_branding_name
Revises: 0285_default_org_branding
Create Date: 2019-04-08 13:23:22.839382

"""
from alembic import op
import sqlalchemy as sa

revision = '0286_unique_email_branding_name'
down_revision = '0285_default_org_branding'


def upgrade():
    op.alter_column('email_branding', 'name',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=False)


def downgrade():
    op.alter_column('email_branding', 'name',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=True)
