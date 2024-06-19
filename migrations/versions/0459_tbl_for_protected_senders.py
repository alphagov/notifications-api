"""

Revision ID: 0459_tbl_for_protected_senders
Revises: 0458_validate_unsub_constraints
Create Date: 2024-06-03 15:17:58.545277

"""

import sqlalchemy as sa
from alembic import op


revision = "0459_tbl_for_protected_senders"
down_revision = "0458_validate_unsub_constraints"


def upgrade():
    op.create_table(
        "protected_sender_ids",
        sa.Column("sender_id", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("sender_id"),
    )


def downgrade():
    op.drop_table("protected_sender_ids")
