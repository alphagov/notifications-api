"""

Revision ID: 0192_drop_provider_statistics
Revises: 0191_ft_billing_pkey
Create Date: 2018-05-21 15:18:43.871256

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0192_drop_provider_statistics'
down_revision = '0191_ft_billing_pkey'


def upgrade():
    op.drop_index('ix_provider_statistics_provider_id', table_name='provider_statistics')
    op.drop_index('ix_provider_statistics_service_id', table_name='provider_statistics')
    op.drop_table('provider_statistics')


def downgrade():
    op.create_table('provider_statistics',
    sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
    sa.Column('day', sa.DATE(), autoincrement=False, nullable=False),
    sa.Column('service_id', postgresql.UUID(), autoincrement=False, nullable=False),
    sa.Column('unit_count', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('provider_id', postgresql.UUID(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['provider_id'], ['provider_details.id'], name='provider_stats_to_provider_fk'),
    sa.ForeignKeyConstraint(['service_id'], ['services.id'], name='provider_statistics_service_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='provider_statistics_pkey')
    )
    op.create_index('ix_provider_statistics_service_id', 'provider_statistics', ['service_id'], unique=False)
    op.create_index('ix_provider_statistics_provider_id', 'provider_statistics', ['provider_id'], unique=False)
