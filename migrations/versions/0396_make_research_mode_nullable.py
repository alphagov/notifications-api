"""

Revision ID: 0396_make_research_mode_nullable
Revises: 0395_migrate_rate_limits
Create Date: 2023-01-11 16:40:21.372085

"""

import sqlalchemy as sa
from alembic import op

revision = "0396_make_research_mode_nullable"
down_revision = "0395_migrate_rate_limits"


def upgrade():
    op.alter_column("services", "research_mode", existing_type=sa.BOOLEAN(), nullable=True)
    op.alter_column("services_history", "research_mode", existing_type=sa.BOOLEAN(), nullable=True)


def downgrade():
    op.execute("UPDATE services SET research_mode = false WHERE research_mode IS NULL")
    op.execute("UPDATE services_history SET research_mode = false WHERE research_mode IS NULL")
    op.alter_column("services", "research_mode", existing_type=sa.BOOLEAN(), nullable=False)
    op.alter_column("services_history", "research_mode", existing_type=sa.BOOLEAN(), nullable=False)
