"""

Revision ID: 0397_drop_research_mode
Revises: 0396_make_research_mode_nullable
Create Date: 2023-01-12 11:43:58.606291

"""

import sqlalchemy as sa
from alembic import op

revision = "0397_drop_research_mode"
down_revision = "0396_make_research_mode_nullable"


def upgrade():
    op.drop_column("services", "research_mode")
    op.drop_column("services_history", "research_mode")


def downgrade():
    op.add_column("services_history", sa.Column("research_mode", sa.BOOLEAN(), nullable=True))
    op.add_column("services", sa.Column("research_mode", sa.BOOLEAN(), nullable=True))
