"""
Create Date: 2025-08-11 11:11:11.111111
"""

from alembic import op
import sqlalchemy as sa

revision = "0511_process_type_nullable"
down_revision = "0510_delete_broadcast_tables"


def upgrade():
    for table in ("templates", "templates_history"):
        op.alter_column(table, "process_type", existing_type=sa.String(), nullable=True)


def downgrade():
    with op.get_context().autocommit_block():
        for table in ("templates", "templates_history"):
            op.execute(f"UPDATE {table} set process_type = 'normal' where process_type is null")
            op.alter_column(table, "process_type", existing_type=sa.String(), nullable=False)
