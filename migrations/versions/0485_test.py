"""
Create Date: 2025-01-09 13:16:56.220349
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0485_test"
down_revision = "0484_rm_daily_sorted_letter"


def upgrade():
    op.create_table(
        "test_migration",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email_address", sa.String(length=255), nullable=False),
    )


def downgrade():
    op.drop_table("test_migration")
