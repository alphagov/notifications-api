"""

Revision ID: 0349_add_ft_processing_time
Revises: 0348_migrate_broadcast_settings
Create Date: 2021-02-22 14:05:24.775338

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0349_add_ft_processing_time"
down_revision = "0348_migrate_broadcast_settings"


def upgrade():
    op.create_table(
        "ft_processing_time",
        sa.Column("bst_date", sa.Date(), nullable=False),
        sa.Column("messages_total", sa.Integer(), nullable=False),
        sa.Column("messages_within_10_secs", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("bst_date"),
    )
    op.create_index(op.f("ix_ft_processing_time_bst_date"), "ft_processing_time", ["bst_date"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_ft_processing_time_bst_date"), table_name="ft_processing_time")
    op.drop_table("ft_processing_time")
