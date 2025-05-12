"""
Create Date: 2025-05-12 17:34:27.333353
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = '0501_drop_inbound_api_table'
down_revision = '0500_update_intl_limit_values'


def upgrade():
    op.drop_index(op.f("ix_service_inbound_api_updated_by_id"), table_name="service_inbound_api")
    op.drop_index(op.f("ix_service_inbound_api_service_id"), table_name="service_inbound_api")
    op.drop_table("service_inbound_api")
    op.drop_index(op.f("ix_service_inbound_api_history_updated_by_id"), table_name="service_inbound_api_history")
    op.drop_index(op.f("ix_service_inbound_api_history_service_id"), table_name="service_inbound_api_history")
    op.drop_table("service_inbound_api_history")


def downgrade():
    op.create_table(
        "service_inbound_api_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("bearer_token", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("id", "version"),
    )
    op.create_index(
        op.f("ix_service_inbound_api_history_service_id"), "service_inbound_api_history", ["service_id"], unique=False
    )
    op.create_index(
        op.f("ix_service_inbound_api_history_updated_by_id"),
        "service_inbound_api_history",
        ["updated_by_id"],
        unique=False,
    )
    op.create_table(
        "service_inbound_api",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("bearer_token", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_service_inbound_api_service_id"), "service_inbound_api", ["service_id"], unique=True)
    op.create_index(
        op.f("ix_service_inbound_api_updated_by_id"), "service_inbound_api", ["updated_by_id"], unique=False
    )
