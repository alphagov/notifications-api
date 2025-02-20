"""
Create Date: 2025-02-18 13:06:49.042094
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0490_create_report_requests"
down_revision = "0489_populate_new_billing_cols"


def upgrade():
    op.create_table("report_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_type", sa.Enum("notifications", name="report_request_report_type"), nullable=False),
        sa.Column("status", sa.Enum("pending", "in progress", "stored", "failed", "deleted", name="report_request_status_type"), nullable=False),
        sa.Column("parameter", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id")
    )


def downgrade():
    op.drop_table("report_requests")
    op.execute("drop type report_request_report_type")
    op.execute("drop type report_request_status_type")
