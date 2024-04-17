"""

Revision ID: 0381_letter_branding_to_org
Revises: 0380_email_branding_cols
Create Date: 2022-10-21 14:26:12.421574

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0381_letter_branding_to_org"
down_revision = "0380_email_branding_cols"


def upgrade():
    op.create_table(
        "letter_branding_to_organisation",
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("letter_branding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["letter_branding_id"],
            ["letter_branding.id"],
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisation.id"],
        ),
        sa.PrimaryKeyConstraint("organisation_id", "letter_branding_id"),
    )


def downgrade():
    op.drop_table("letter_branding_to_organisation")
