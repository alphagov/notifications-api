"""

Revision ID: 0355_add_webauthn_table
Revises: 0354_government_channel
Create Date: 2021-05-07 17:04:22.017137

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0355_add_webauthn_table"
down_revision = "0354_government_channel"


def upgrade():
    op.create_table(
        "webauthn_credential",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("credential_data", sa.String(), nullable=False),
        sa.Column("registration_response", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("webauthn_credential")
