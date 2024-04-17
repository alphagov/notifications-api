"""

Revision ID: 0319_contact_list_archived
Revises: 0318_service_contact_list
Create Date: 2020-03-26 11:16:12.389524

"""

import sqlalchemy as sa
from alembic import op

revision = "0319_contact_list_archived"
down_revision = "0318_service_contact_list"


def upgrade():
    op.add_column(
        "service_contact_list",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column(
        "service_contact_list",
        "archived",
    )
