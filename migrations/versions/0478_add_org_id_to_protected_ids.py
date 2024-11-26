"""
Create Date: 2024-11-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0478_add_org_id_to_protected_ids"
down_revision = "0477_create_sjr_contacted_users"


def upgrade():
    op.add_column(
        "protected_sender_ids",
        sa.Column(
            "organisation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organisation.id"),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("protected_sender_ids", "organisation_id")
