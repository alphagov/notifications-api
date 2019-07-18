"""

Revision ID: 0299_org_types_table
Revises: 0298_add_mou_signed_receipt
Create Date: 2019-07-10 16:07:22.019759

"""
from alembic import op
import sqlalchemy as sa


revision = '0299_org_types_table'
down_revision = '0298_add_mou_signed_receipt'


def upgrade():
    organisation_types_table = op.create_table(
        'organisation_types',
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('name'),
        sa.Column('is_crown', sa.Boolean, nullable=True),
        sa.Column('annual_free_sms_fragment_limit', sa.BigInteger, nullable=False)

    )

    op.bulk_insert(
        organisation_types_table,
        [
            {'name': x, 'is_crown': y, 'annual_free_sms_fragment_limit': z} for x, y, z in [
                ["central", None, 250000],
                ["local", False, 25000],
                ["nhs_central", True, 250000],
                ["nhs_local", False, 25000],
                ["emergency_service", False, 25000],
                ["school_or_college", False, 25000],
                ["other", None, 25000],
            ]
        ]
    )
    op.alter_column('services', 'crown', nullable=True)
    op.alter_column('services_history', 'crown', nullable=True)


def downgrade():
    op.execute('DROP TABLE organisation_types')
