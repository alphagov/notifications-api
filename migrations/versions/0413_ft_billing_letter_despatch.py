"""

Revision ID: 0413_ft_billing_letter_despatch
Revises: 0412_letter_despatch
Create Date: 2023-05-24 08:42:11.354797

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0413_ft_billing_letter_despatch"
down_revision = "0412_letter_despatch"


def upgrade():
    op.create_table(
        "ft_billing_letter_despatch",
        sa.Column("bst_date", sa.Date(), nullable=False),
        sa.Column("postage", sa.String(), nullable=False),
        sa.Column(
            "cost_threshold", postgresql.ENUM(name="letter_despatch_cost_threshold", create_type=False), nullable=False
        ),
        sa.Column("rate", sa.Numeric(), nullable=False),
        sa.Column("billable_units", sa.Integer(), nullable=True),
        sa.Column("notifications_sent", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("bst_date", "postage", "rate", "billable_units", "cost_threshold"),
    )


def downgrade():
    op.drop_table("ft_billing_letter_despatch")
