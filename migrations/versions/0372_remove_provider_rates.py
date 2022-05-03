"""

Revision ID: 0372_remove_provider_rates
Revises: 0371_fix_apr_2022_sms_rate
Create Date: 2022-04-26 09:39:45.260951

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0372_remove_provider_rates'
down_revision = '0371_fix_apr_2022_sms_rate'


def upgrade():
    op.drop_table('provider_rates')


def downgrade():
    op.create_table(
        'provider_rates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('valid_from', sa.DateTime(), nullable=False),
        sa.Column('provider_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('rate', sa.Numeric(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['provider_id'], ['provider_details.id'], ),
    )
