"""
Create Date: 2024-10-21 10:07:03.303036
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0468_test"
down_revision = "0467_svc_join_approved_tmp"


def upgrade():
    op.create_table(
        "test_table",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
    )


def downgrade():
    op.drop_table("test_table")
