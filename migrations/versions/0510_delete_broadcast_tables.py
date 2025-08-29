"""
Create Date: 2025-08-07 11:08:46.900469
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0510_delete_broadcast_tables"
down_revision = "0509_delete_broadcast_data"


def upgrade():
    op.drop_table("service_broadcast_settings")
    op.drop_table("broadcast_channel_types")
    op.drop_table("broadcast_provider_message_number")
    op.drop_table("broadcast_provider_message")
    op.drop_table("broadcast_event")
    op.drop_table("broadcast_provider_message_status_type")
    op.drop_table("broadcast_message")
    op.drop_table("broadcast_provider_types")
    op.drop_table("service_broadcast_provider_restriction")
    op.drop_table("broadcast_status_type")
    op.drop_column("templates", "broadcast_data")
    op.drop_column("templates_history", "broadcast_data")


def downgrade():
    op.add_column(
        "templates_history",
        sa.Column("broadcast_data", postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True),
    )
    op.add_column(
        "templates",
        sa.Column("broadcast_data", postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True),
    )

    op.create_table(
        "broadcast_provider_message_status_type",
        sa.Column("name", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("name", name="broadcast_provider_message_status_type_pkey"),
    )
    op.create_table(
        "broadcast_status_type",
        sa.Column("name", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("name", name="broadcast_status_type_pkey"),
        postgresql_ignore_search_path=False,
    )
    op.create_table(
        "service_broadcast_provider_restriction",
        sa.Column("service_id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("provider", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["service_id"], ["services.id"], name="service_broadcast_provider_restriction_service_id_fkey"
        ),
        sa.PrimaryKeyConstraint("service_id", name="service_broadcast_provider_restriction_pkey"),
    )
    op.create_table(
        "broadcast_provider_types",
        sa.Column("name", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("name", name="broadcast_provider_types_pkey"),
        postgresql_ignore_search_path=False,
    )
    op.create_table(
        "broadcast_message",
        sa.Column("id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("service_id", postgresql.UUID(), autoincrement=False, nullable=True),
        sa.Column("template_id", postgresql.UUID(), autoincrement=False, nullable=True),
        sa.Column("template_version", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("_personalisation", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column("areas", postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=False),
        sa.Column("status", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("starts_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column("finishes_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column("approved_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column("cancelled_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column("updated_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column("created_by_id", postgresql.UUID(), autoincrement=False, nullable=True),
        sa.Column("approved_by_id", postgresql.UUID(), autoincrement=False, nullable=True),
        sa.Column("cancelled_by_id", postgresql.UUID(), autoincrement=False, nullable=True),
        sa.Column("content", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("reference", sa.VARCHAR(length=255), autoincrement=False, nullable=True),
        sa.Column("stubbed", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column("cap_event", sa.VARCHAR(length=255), autoincrement=False, nullable=True),
        sa.Column("created_by_api_key_id", postgresql.UUID(), autoincrement=False, nullable=True),
        sa.Column("cancelled_by_api_key_id", postgresql.UUID(), autoincrement=False, nullable=True),
        sa.CheckConstraint(
            "(created_by_id IS NOT NULL) OR (created_by_api_key_id IS NOT NULL)",
            name="ck_broadcast_message_created_by_not_null",
        ),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], name="broadcast_message_approved_by_id_fkey"),
        sa.ForeignKeyConstraint(
            ["cancelled_by_api_key_id"], ["api_keys.id"], name="broadcast_message_cancelled_by_api_key_id_fkey"
        ),
        sa.ForeignKeyConstraint(["cancelled_by_id"], ["users.id"], name="broadcast_message_cancelled_by_id_fkey"),
        sa.ForeignKeyConstraint(
            ["created_by_api_key_id"], ["api_keys.id"], name="broadcast_message_created_by_api_key_id_fkey"
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="broadcast_message_created_by_id_fkey"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], name="broadcast_message_service_id_fkey"),
        sa.ForeignKeyConstraint(["status"], ["broadcast_status_type.name"], name="broadcast_message_status_fkey"),
        sa.ForeignKeyConstraint(
            ["template_id", "template_version"],
            ["templates_history.id", "templates_history.version"],
            name="broadcast_message_template_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="broadcast_message_pkey"),
    )
    op.create_table(
        "broadcast_event",
        sa.Column("id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("service_id", postgresql.UUID(), autoincrement=False, nullable=True),
        sa.Column("broadcast_message_id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("sent_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column("message_type", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("transmitted_content", postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True),
        sa.Column("transmitted_areas", postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=False),
        sa.Column("transmitted_sender", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("transmitted_starts_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column("transmitted_finishes_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(
            ["broadcast_message_id"], ["broadcast_message.id"], name="broadcast_event_broadcast_message_id_fkey"
        ),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], name="broadcast_event_service_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="broadcast_event_pkey"),
        postgresql_ignore_search_path=False,
    )
    op.create_table(
        "broadcast_provider_message",
        sa.Column("id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("broadcast_event_id", postgresql.UUID(), autoincrement=False, nullable=True),
        sa.Column("provider", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column("status", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(
            ["broadcast_event_id"], ["broadcast_event.id"], name="broadcast_provider_message_broadcast_event_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="broadcast_provider_message_pkey"),
        sa.UniqueConstraint(
            "broadcast_event_id", "provider", name="broadcast_provider_message_broadcast_event_id_provider_key"
        ),
        postgresql_ignore_search_path=False,
    )
    op.create_table(
        "broadcast_provider_message_number",
        sa.Column(
            "broadcast_provider_message_number",
            sa.INTEGER(),
            server_default=sa.text("nextval('broadcast_provider_message_number_seq'::regclass)"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("broadcast_provider_message_id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["broadcast_provider_message_id"],
            ["broadcast_provider_message.id"],
            name="broadcast_provider_message_nu_broadcast_provider_message_i_fkey",
        ),
        sa.PrimaryKeyConstraint("broadcast_provider_message_number", name="broadcast_provider_message_number_pkey"),
    )
    op.create_table(
        "broadcast_channel_types",
        sa.Column("name", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("name", name="broadcast_channel_types_pkey"),
    )
    op.create_table(
        "service_broadcast_settings",
        sa.Column("service_id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("channel", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column("provider", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["channel"], ["broadcast_channel_types.name"], name="service_broadcast_settings_channel_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["provider"], ["broadcast_provider_types.name"], name="service_broadcast_settings_provider_fkey"
        ),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], name="service_broadcast_settings_service_id_fkey"),
        sa.PrimaryKeyConstraint("service_id", name="service_broadcast_settings_pkey"),
    )
