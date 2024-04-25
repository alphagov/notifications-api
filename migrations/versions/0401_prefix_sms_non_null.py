"""

Revision ID: 0401_prefix_sms_non_null
Revises: 0400_non_nullable_ids
Create Date: 2023-01-19 16:56:49.635251

"""

import sqlalchemy as sa
from alembic import op

revision = "0401_prefix_sms_non_null"
down_revision = "0400_non_nullable_ids"


def upgrade():
    op.execute("UPDATE services_history SET prefix_sms = FALSE WHERE prefix_sms IS NULL")
    op.alter_column("services_history", "prefix_sms", existing_type=sa.BOOLEAN(), nullable=False)


def downgrade():
    op.alter_column("services_history", "prefix_sms", existing_type=sa.BOOLEAN(), nullable=True)
