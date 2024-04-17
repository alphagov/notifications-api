"""

Revision ID: 0240_dvla_org_non_nullable
Revises: 0239_add_edit_folder_permission
Create Date: 2018-10-25 09:16:54.602182

"""

import sqlalchemy as sa
from alembic import op

revision = "0240_dvla_org_non_nullable"
down_revision = "0239_add_edit_folder_permission"


def upgrade():
    op.alter_column("dvla_organisation", "filename", existing_type=sa.VARCHAR(length=255), nullable=False)
    op.alter_column("dvla_organisation", "name", existing_type=sa.VARCHAR(length=255), nullable=False)


def downgrade():
    op.alter_column("dvla_organisation", "name", existing_type=sa.VARCHAR(length=255), nullable=True)
    op.alter_column("dvla_organisation", "filename", existing_type=sa.VARCHAR(length=255), nullable=True)
