"""

Revision ID: 0412_letter_despatch
Revises: 0411_contact_list_idx
Create Date: 2023-05-22 15:41:45.251681

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0412_letter_despatch"
down_revision = "0411_contact_list_idx"


def upgrade():
    op.create_table(
        "notifications_letter_despatch",
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("despatched_on", sa.Date(), nullable=True),
        sa.Column(
            "cost_threshold", sa.Enum("sorted", "unsorted", name="letter_despatch_cost_threshold"), nullable=False
        ),
        sa.PrimaryKeyConstraint("notification_id"),
    )
    op.create_index(
        op.f("ix_notifications_letter_despatch_cost_threshold"),
        "notifications_letter_despatch",
        ["cost_threshold"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notifications_letter_despatch_despatched_on"),
        "notifications_letter_despatch",
        ["despatched_on"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_notifications_letter_despatch_despatched_on"), table_name="notifications_letter_despatch")
    op.drop_index(op.f("ix_notifications_letter_despatch_cost_threshold"), table_name="notifications_letter_despatch")
    op.drop_table("notifications_letter_despatch")
    sa.Enum(name="letter_despatch_cost_threshold").drop(op.get_bind(), checkfirst=False)
