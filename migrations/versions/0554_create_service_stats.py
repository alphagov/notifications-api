"""
Create service_stats table for aggregated notification status counts.

Revision ID: 0554_create_service_stats
Revises: 0553_notifications_id_status_idx
Create Date: 2026-05-19 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0554_create_service_stats"
down_revision = "0553_notifications_id_status_idx"


def upgrade():
    op.create_table(
        "service_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", postgresql.ENUM(name="notification_type", create_type=False), nullable=False),
        sa.Column("notification_status", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"]),
        sa.ForeignKeyConstraint(["notification_status"], ["notification_status_types.name"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service_id",
            "template_id",
            "notification_type",
            "notification_status",
            name="uix_service_stats_dimensions",
        ),
    )

    op.create_index(
        "ix_svc_stats_svc_ntype_nstatus",
        "service_stats",
        ["service_id", "notification_type", "notification_status"],
        unique=False,
    )
    op.create_index(
        "ix_svc_stats_tmpl_ntype_nstatus",
        "service_stats",
        ["template_id", "notification_type", "notification_status"],
        unique=False,
    )
    op.create_index(
        "ix_service_stats_service_id_template_id",
        "service_stats",
        ["service_id", "template_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_service_stats_service_id_template_id", table_name="service_stats")
    op.drop_index(
        "ix_svc_stats_tmpl_ntype_nstatus",
        table_name="service_stats",
    )
    op.drop_index(
        "ix_svc_stats_svc_ntype_nstatus",
        table_name="service_stats",
    )
    op.drop_table("service_stats")
