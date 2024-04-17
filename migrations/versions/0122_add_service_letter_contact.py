"""

Revision ID: 0122_add_service_letter_contact
Revises: 0121_nullable_logos
Create Date: 2017-09-21 12:16:02.975120

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0122_add_service_letter_contact"
down_revision = "0121_nullable_logos"


def upgrade():
    op.create_table(
        "service_letter_contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_block", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_service_letter_contact_service_id"), "service_letter_contacts", ["service_id"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_service_letter_contact_service_id"), table_name="service_letter_contacts")
    op.drop_table("service_letter_contacts")
