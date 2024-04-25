"""

Revision ID: 0399_nullable_message_limit
Revises: 0395_migrate_rate_limits
Create Date: 2023-01-18 13:13:06.439154

"""

import sqlalchemy as sa
from alembic import op

revision = "0399_nullable_message_limit"
down_revision = "0398_active_email_branding"


def upgrade():
    op.alter_column("services", "message_limit", existing_type=sa.BIGINT(), nullable=True)
    op.alter_column("services_history", "message_limit", existing_type=sa.BIGINT(), nullable=True)


def downgrade():
    op.execute(
        """
        UPDATE services_history
        SET message_limit = (CASE restricted WHEN true THEN 50 ELSE 250000 END)
        WHERE message_limit IS NULL
        """
    )
    op.execute(
        """
        UPDATE services
        SET message_limit = (CASE restricted WHEN true THEN 50 ELSE 250000 END)
        WHERE message_limit IS NULL
        """
    )
    op.alter_column("services_history", "message_limit", existing_type=sa.BIGINT(), nullable=False)
    op.alter_column("services", "message_limit", existing_type=sa.BIGINT(), nullable=False)
