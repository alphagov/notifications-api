"""

Revision ID: 0352_broadcast_provider_types
Revises: 0351_unique_key_annual_billing
Create Date: 2021-05-05 15:07:22.146657

"""

import sqlalchemy as sa
from alembic import op

revision = "0352_broadcast_provider_types"
down_revision = "0351_unique_key_annual_billing"

PROVIDER_TYPES = ("ee", "three", "vodafone", "o2", "all")


def upgrade():
    op.create_table(
        "broadcast_provider_types",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    for provider in PROVIDER_TYPES:
        op.execute(f"INSERT INTO broadcast_provider_types VALUES ('{provider}')")
    op.create_foreign_key(
        "service_broadcast_settings_provider_fkey",
        "service_broadcast_settings",
        "broadcast_provider_types",
        ["provider"],
        ["name"],
    )


def downgrade():
    op.drop_constraint("service_broadcast_settings_provider_fkey", "service_broadcast_settings", type_="foreignkey")
    op.drop_table("broadcast_provider_types")
