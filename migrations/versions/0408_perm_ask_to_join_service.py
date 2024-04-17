"""

Revision ID: 0407_letter_attachments
Revises: 0406_1_april_2023_sms_rates
Create Date: 2023-03-09 08:45:00.990562

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0408_perm_ask_to_join_service"
down_revision = "0407_letter_attachments"


def upgrade():
    op.create_table(
        "organisation_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "permission",
            sa.Enum(
                "can_ask_to_join_a_service",
                name="organisation_permission_types",
            ),
            nullable=False,
        ),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisation.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("organisation_permissions")
    op.execute("drop type organisation_permission_types")
