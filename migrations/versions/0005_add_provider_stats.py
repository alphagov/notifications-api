"""empty message

Revision ID: 0005_add_provider_stats
Revises: 0003_add_service_history
Create Date: 2016-04-20 15:13:42.229197

"""

# revision identifiers, used by Alembic.
revision = '0005_add_provider_stats'
down_revision = '0004_notification_stats_date'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table('provider_rates',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('valid_from', sa.DateTime(), nullable=False),
    sa.Column('provider', sa.Enum('mmg', 'twilio', 'firetext', 'ses', name='providers'), nullable=False),
    sa.Column('rate', sa.Numeric(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('provider_statistics',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('provider', sa.Enum('mmg', 'twilio', 'firetext', 'ses', name='providers'), nullable=False),
    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('unit_count', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_provider_statistics_service_id'), 'provider_statistics', ['service_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_provider_statistics_service_id'), table_name='provider_statistics')
    op.drop_table('provider_statistics')
    op.drop_table('provider_rates')
