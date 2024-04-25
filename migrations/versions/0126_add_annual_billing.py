"""

Revision ID: 0126_add_annual_billing
Revises: 0125_add_organisation_type
Create Date: 2017-10-19 11:38:32.849573

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0126_add_annual_billing"
down_revision = "0125_add_organisation_type"


def upgrade():
    op.create_table(
        "annual_billing",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("financial_year_start", sa.Integer(), nullable=False),
        sa.Column("free_sms_fragment_limit", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_annual_billing_service_id"), "annual_billing", ["service_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_annual_billing_service_id"), table_name="annual_billing")
    op.drop_table("annual_billing")
