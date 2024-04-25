"""

Revision ID: 0392_go_live_cols_non_nullable
Revises: 0391_add_go_live_columns
Create Date: 2022-12-20 08:01:58.001061

"""

import sqlalchemy as sa
from alembic import op

revision = "0392_go_live_cols_non_nullable"
down_revision = "0391_add_go_live_columns"


columns_to_make_non_nullable = (
    ("services", "has_active_go_live_request"),
    ("services_history", "has_active_go_live_request"),
    ("organisation", "can_approve_own_go_live_requests"),
)


def upgrade():
    for table, column in columns_to_make_non_nullable:
        op.execute(f"UPDATE {table} SET {column} = false")
        op.alter_column(table, column, existing_type=sa.BOOLEAN(), nullable=False)


def downgrade():
    for table, column in columns_to_make_non_nullable:
        op.alter_column(table, column, existing_type=sa.BOOLEAN(), nullable=True)
        op.execute(f"UPDATE {table} SET {column} = null")
