"""

Revision ID: 0400_non_nullable_ids
Revises: 0399_nullable_message_limit
Create Date: 2023-01-19 16:13:38.601465

"""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0400_non_nullable_ids"
down_revision = "0399_nullable_message_limit"


def upgrade():
    op.alter_column("user_to_service", "user_id", existing_type=postgresql.UUID(), nullable=False)
    op.alter_column("user_to_service", "service_id", existing_type=postgresql.UUID(), nullable=False)


def downgrade():
    op.alter_column("user_to_service", "service_id", existing_type=postgresql.UUID(), nullable=True)
    op.alter_column("user_to_service", "user_id", existing_type=postgresql.UUID(), nullable=True)
