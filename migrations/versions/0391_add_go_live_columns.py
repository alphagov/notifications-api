"""

Revision ID: 0391_add_go_live_columns
Revises: 0390_require_rate_limit_value
Create Date: 2022-12-19 08:01:58.001061

"""

import sqlalchemy as sa
from alembic import op

revision = "0391_add_go_live_columns"
down_revision = "0390_require_rate_limit_value"


def upgrade():
    op.add_column("services", sa.Column("has_active_go_live_request", sa.Boolean(), nullable=True))
    op.add_column("services_history", sa.Column("has_active_go_live_request", sa.Boolean(), nullable=True))

    op.add_column("organisation", sa.Column("can_approve_own_go_live_requests", sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column("services_history", "has_active_go_live_request")
    op.drop_column("services", "has_active_go_live_request")

    op.drop_column("organisation", "can_approve_own_go_live_requests")
