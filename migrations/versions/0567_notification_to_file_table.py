"""
Create Date: 2026-09-08 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0567_notification_to_file_table"
down_revision = "0566_add_api_key_usg_xstats_dep"


def upgrade():
    op.create_table("sent_files",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("document_id"),
        sa.ForeignKeyConstraint(
                    ["service_id"],
                    ["services.id"],
                ),
    )
    op.create_index(op.f("ix_sent_files_service_id"), "sent_files", ["service_id"], unique=False)
    op.create_index(op.f("ix_sent_files_notification_id"), "sent_files", ["notification_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_sent_files_notification_id"), table_name="sent_files")
    op.drop_index(op.f("ix_sent_files_service_id"), table_name="sent_files")
    op.drop_table("sent_files")
