"""

Revision ID: 0126_add_annual_billing
Revises: 0125_add_organisation_type
Create Date: 2017-10-18 11:42:54.261575

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0126_add_annual_billing'
down_revision = '0125_add_organisation_type'


def upgrade():
    op.create_table('annual_billing',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('financial_year_start', sa.Integer(), nullable=False),
    sa.Column('free_sms_fragment_limit', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
    sa.PrimaryKeyConstraint('id'))


def downgrade():
    op.drop_table('annual_billing')
