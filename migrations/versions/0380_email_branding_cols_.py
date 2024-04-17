"""
Revision ID: 0380_email_branding_cols
Revises: 0379_update_archived_users
Create Date: 2022-10-19 12:12:15.225244
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0380_email_branding_cols"
down_revision = "0379_update_archived_users"


def upgrade():
    op.add_column("email_branding", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.add_column("email_branding", sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("email_branding", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("email_branding", sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("email_branding_updated_by_id_fkey", "email_branding", "users", ["updated_by"], ["id"])
    op.create_foreign_key("email_branding_created_by_id_fkey", "email_branding", "users", ["created_by"], ["id"])


def downgrade():
    op.drop_constraint("email_branding_created_by_id_fkey", "email_branding", type_="foreignkey")
    op.drop_constraint("email_branding_updated_by_id_fkey", "email_branding", type_="foreignkey")
    op.drop_column("email_branding", "updated_by")
    op.drop_column("email_branding", "updated_at")
    op.drop_column("email_branding", "created_by")
    op.drop_column("email_branding", "created_at")
