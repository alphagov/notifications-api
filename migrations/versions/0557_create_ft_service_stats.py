"""
Create Date: 2026-07-22T00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0557_create_ft_service_stats"
down_revision = "0556_add_notify_status_idx"


def upgrade():
    op.create_table(
        "ft_service_stats",
        sa.Column("bst_date", sa.Date(), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", postgresql.ENUM(name="notification_type", create_type=False), nullable=False),
        sa.Column("notification_status", sa.Text(), nullable=False),
        sa.Column("notification_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"]),
        sa.ForeignKeyConstraint(["notification_status"], ["notification_status_types.name"]),
        sa.PrimaryKeyConstraint(
            "bst_date",
            "service_id",
            "template_id",
            "notification_type",
            "notification_status",
        ),
    )

    op.create_index(
        "ix_ft_service_stats",
        "ft_service_stats",
        ["bst_date", "service_id", "template_id", "notification_type", "notification_status"],
        unique=True,
    )

    op.create_index(
        "ix_ft_service_template_stats",
        "ft_service_stats",
        ["bst_date", "template_id", "notification_type", "notification_status"],
        unique=True,
    )

def downgrade():
    op.drop_index("ix_ft_service_template_stats", table_name="ft_service_stats")
    op.drop_index("ix_ft_service_stats", table_name="ft_service_stats")
    op.drop_table("ft_service_stats")
