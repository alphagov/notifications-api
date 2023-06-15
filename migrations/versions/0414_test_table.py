"""

Revision ID: 0414_test_table
Revises: 0413_ft_billing_letter_despatch
Create Date: 2023-06-15 09:40:55.990235

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0414_test_table"
down_revision = "0413_ft_billing_letter_despatch"


def upgrade():
    op.create_table(
        "table_owner_permissions_test",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("table_owner_permissions_test")
