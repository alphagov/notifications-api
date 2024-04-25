"""

Revision ID: 0410_drop_unused_allowance
Revises: 0409_annual_allowance
Create Date: 2023-04-26 07:52:19.822068

"""

from alembic import op
import sqlalchemy as sa


revision = "0410_drop_unused_allowance"
down_revision = "0409_annual_allowance"


def upgrade():
    op.drop_column("organisation_types", "annual_free_sms_fragment_limit")


def downgrade():
    op.add_column(
        "organisation_types",
        sa.Column("annual_free_sms_fragment_limit", sa.BIGINT(), autoincrement=False, nullable=True),
    )
    op.execute("UPDATE organisation_types SET annual_free_sms_fragment_limit = 250000 WHERE name = 'central'")
    op.execute("UPDATE organisation_types SET annual_free_sms_fragment_limit = 25000 WHERE name = 'local'")
    op.execute("UPDATE organisation_types SET annual_free_sms_fragment_limit = 25000 WHERE name = 'nhs'")
    op.execute("UPDATE organisation_types SET annual_free_sms_fragment_limit = 250000 WHERE name = 'nhs_central'")
    op.execute("UPDATE organisation_types SET annual_free_sms_fragment_limit = 25000 WHERE name = 'nhs_local'")
    op.execute("UPDATE organisation_types SET annual_free_sms_fragment_limit = 25000 WHERE name = 'nhs_gp'")
    op.execute("UPDATE organisation_types SET annual_free_sms_fragment_limit = 25000 WHERE name = 'emergency_service'")
    op.execute("UPDATE organisation_types SET annual_free_sms_fragment_limit = 25000 WHERE name = 'school_or_college'")
    op.execute("UPDATE organisation_types SET annual_free_sms_fragment_limit = 25000 WHERE name = 'other'")
    op.alter_column("organisation_types", "annual_free_sms_fragment_limit", nullable=False)
