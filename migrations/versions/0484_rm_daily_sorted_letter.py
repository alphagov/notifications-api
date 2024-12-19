"""
Create Date: 2024-12-17 15:12:04.205888
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0484_rm_daily_sorted_letter"
down_revision = "0483_rm_ntfcn_service_composite"


def upgrade():
    op.drop_index("ix_daily_sorted_letter_billing_day", table_name="daily_sorted_letter")
    op.drop_table("daily_sorted_letter")


def downgrade():
    op.create_table(
        "daily_sorted_letter",
        sa.Column("id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("billing_day", sa.DATE(), autoincrement=False, nullable=False),
        sa.Column("unsorted_count", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("sorted_count", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column("file_name", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint("id", name="daily_sorted_letter_pkey"),
        sa.UniqueConstraint("file_name", "billing_day", name="uix_file_name_billing_day"),
    )
    op.create_index("ix_daily_sorted_letter_billing_day", "daily_sorted_letter", ["billing_day"], unique=False)
