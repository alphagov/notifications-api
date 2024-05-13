"""
Create Date: 2024-05-13 13:53:11.227939
"""

from alembic import op
import sqlalchemy as sa


revision = "0444_user_features_email_column"
down_revision = "0443_drop_ix_letter_cost"


def upgrade():
    op.add_column(
        "users", sa.Column("receives_new_features_email", sa.Boolean(), nullable=False, server_default=sa.true())
    )


def downgrade():
    op.drop_column("users", "receives_new_features_email")
