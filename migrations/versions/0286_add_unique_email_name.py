"""

Revision ID: 0286_add_unique_email_name
Revises: 0285_default_org_branding
Create Date: 2019-04-09 13:01:13.892249

"""
from alembic import op
import sqlalchemy as sa

revision = '0286_add_unique_email_name'
down_revision = '0285_default_org_branding'


def upgrade():
    op.alter_column('email_branding', 'name',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=False)
    op.create_unique_constraint('uq_email_branding_name', 'email_branding', ['name'])


def downgrade():
    op.drop_constraint('uq_email_branding_name', 'email_branding', type_='unique')
    op.alter_column('email_branding', 'name',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=True)
