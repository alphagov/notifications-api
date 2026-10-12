"""
Create Date: 2026-10-12 15:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0578_drop_ft_service_stats'
down_revision = '0577_add_ft_notif_status_live'


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_ft_service_template_stats")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_ft_service_stats")

    if op.get_context().as_sql:
        op.get_context().impl.static_output("-- squawk-ignore-file ban-drop-table")

    op.drop_table("ft_service_stats")


def downgrade():
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
