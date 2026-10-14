"""
Create Date: 2026-10-12 15:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0577_add_ft_notif_status_live'
down_revision = '0576_alter_usage_hour'

# For Reference, this PR is made from the following migrations:
# - migrations/versions/0188_add_ft_notification_status.py
# - migrations/versions/0195_ft_notification_timestamps.py
# - migrations/versions/0472_ft_ntfcn_status_xstats_deps.py
# - migrations/versions/0482_ft_ntfcn_stat_tpt_date_idx.py

def upgrade():
    if op.get_context().as_sql:
        # column types match the other ft_* tables
        op.get_context().impl.static_output("-- squawk-ignore-file prefer-timestamp-tz, prefer-bigint-over-int")

    op.create_table(
        "ft_notification_status_live",
        sa.Column("bst_date", sa.Date(), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.Text(), nullable=False),
        sa.Column("key_type", sa.Text(), nullable=False),
        sa.Column("notification_status", sa.Text(), nullable=False),
        sa.Column("notification_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint(
            "bst_date", "template_id", "service_id", "job_id", "notification_type", "key_type", "notification_status"
        ),
    )

    # Create indexes for the ft_notification_status_live table
    op.create_index(op.f("ix_ft_notification_status_live_bst_date"), "ft_notification_status_live", ["bst_date"], unique=False)
    op.create_index(op.f("ix_ft_notification_status_live_job_id"), "ft_notification_status_live", ["job_id"], unique=False)
    op.create_index(
        op.f("ix_ft_notification_status_live_service_id"), "ft_notification_status_live", ["service_id"], unique=False
    )
    op.create_index(
        op.f("ix_ft_notification_status_live_template_id"), "ft_notification_status_live", ["template_id"], unique=False
    )
    op.create_index(
        op.f("ix_ft_notification_status_live_template_id_bst_date"), "ft_notification_status_live", ["template_id", "bst_date"], unique=False
    )

    # Create statistics for the ft_notification_status_live table
    op.execute(
        "CREATE STATISTICS st_dep_ft_notif_status_live_service_id_job_id (dependencies) ON service_id, job_id FROM ft_notification_status_live"
    )
    op.execute(
        "CREATE STATISTICS st_dep_ft_notif_status_live_service_id_template_id (dependencies) ON service_id, template_id FROM ft_notification_status_live"
    )
    op.execute(
        "CREATE STATISTICS st_dep_ft_notif_status_live_job_id_template_id_ntfcn_type (dependencies) ON job_id, template_id, notification_type FROM ft_notification_status_live"
    )


def downgrade():
    # Drop statistics for the ft_notification_status_live table
    op.execute("DROP STATISTICS st_dep_ft_notif_status_live_service_id_job_id")
    op.execute("DROP STATISTICS st_dep_ft_notif_status_live_service_id_template_id")
    op.execute("DROP STATISTICS st_dep_ft_notif_status_live_job_id_template_id_ntfcn_type")

    # Drop indexes for the ft_notification_status_live table
    op.drop_index(op.f("ix_ft_notification_status_live_bst_date"), table_name="ft_notification_status_live")
    op.drop_index(op.f("ix_ft_notification_status_live_job_id"), table_name="ft_notification_status_live")
    op.drop_index(op.f("ix_ft_notification_status_live_service_id"), table_name="ft_notification_status_live")
    op.drop_index(op.f("ix_ft_notification_status_live_template_id"), table_name="ft_notification_status_live")
    op.drop_index(op.f("ix_ft_notification_status_live_template_id_bst_date"), table_name="ft_notification_status_live")

    # Drop the ft_notification_status_live table
    op.drop_table("ft_notification_status_live")
