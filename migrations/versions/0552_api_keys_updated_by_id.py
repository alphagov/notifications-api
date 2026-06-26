"""
Revision ID: 0552_api_keys_updated_by_id
Revises: 0551_drop_ntfcns_failed_idx
Create Date: 2026-06-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0552_api_keys_updated_by_id"
down_revision = "0551_drop_ntfcns_failed_idx"


def upgrade():
    op.add_column("api_keys", sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_api_keys_updated_by_id"), "api_keys", ["updated_by_id"], unique=False)
    op.create_foreign_key("fk_api_keys_updated_by_id", "api_keys", "users", ["updated_by_id"], ["id"])

    op.add_column("api_keys_history", sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade():
    op.drop_column("api_keys_history", "updated_by_id")

    op.drop_constraint("fk_api_keys_updated_by_id", "api_keys", type_="foreignkey")
    op.drop_index(op.f("ix_api_keys_updated_by_id"), table_name="api_keys")
    op.drop_column("api_keys", "updated_by_id")
