"""
Create Date: 2024-10-15 12:21:32.071832
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0465_rename_svc_join_enum"
down_revision = "0464_create_svc_join_requests"


def upgrade():
    op.execute("ALTER TYPE request_status RENAME TO service_join_requests_status_type")


def downgrade():
    op.execute("ALTER TYPE service_join_requests_status_type RENAME TO request_status")
