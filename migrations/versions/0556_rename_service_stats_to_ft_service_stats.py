"""
Rename service_stats table to ft_service_stats.

Revision ID: 0556_rename_service_stats_to_fts
Revises: 0555_notif_replica_identity
Create Date: 2026-05-22 00:00:00
"""

from alembic import op

revision = "0556_rename_service_stats_to_fts"
down_revision = "0555_notif_replica_identity"


def upgrade():
    op.rename_table("service_stats", "ft_service_stats")

    op.execute(
        "ALTER TABLE ft_service_stats "
        "RENAME CONSTRAINT uix_service_stats_dimensions TO uix_ft_service_stats_dimensions"
    )

    op.execute("ALTER INDEX ix_svc_stats_svc_ntype_nstatus RENAME TO ix_ft_svc_stats_svc_ntype_nstatus")
    op.execute("ALTER INDEX ix_svc_stats_tmpl_ntype_nstatus RENAME TO ix_ft_svc_stats_tmpl_ntype_nstatus")
    op.execute(
        "ALTER INDEX ix_service_stats_service_id_template_id "
        "RENAME TO ix_ft_service_stats_service_id_template_id"
    )


def downgrade():
    op.execute(
        "ALTER INDEX ix_ft_service_stats_service_id_template_id "
        "RENAME TO ix_service_stats_service_id_template_id"
    )
    op.execute("ALTER INDEX ix_ft_svc_stats_tmpl_ntype_nstatus RENAME TO ix_svc_stats_tmpl_ntype_nstatus")
    op.execute("ALTER INDEX ix_ft_svc_stats_svc_ntype_nstatus RENAME TO ix_svc_stats_svc_ntype_nstatus")

    op.execute(
        "ALTER TABLE ft_service_stats "
        "RENAME CONSTRAINT uix_ft_service_stats_dimensions TO uix_service_stats_dimensions"
    )

    op.rename_table("ft_service_stats", "service_stats")
