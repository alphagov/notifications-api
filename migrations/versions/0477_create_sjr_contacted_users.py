"""
Create Date: 2024-11-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0477_create_sjr_contacted_users"
down_revision = "0476_notifications_failed_idx"


def upgrade():
    # 1. Create service_join_request_contacted_users
    op.create_table(
        "service_join_request_contacted_users",
        sa.Column(
            "service_join_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_join_requests.id"),
            primary_key=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
    )

    # 2. Copy data from the old table to the new
    op.execute(
        """
        INSERT INTO service_join_request_contacted_users (service_join_request_id, user_id)
        SELECT service_join_request_id, user_id FROM contacted_users;
        """
    )


def downgrade():
    op.drop_table("service_join_request_contacted_users")
