"""
Create Date: 2026-09-08 13:11:02.589651
"""

from alembic import op
import sqlalchemy as sa

revision = '0564_add_api_key_usage_table'
down_revision = '0563_confirmed_service_name_col'


def upgrade():
    op.create_table('api_key_usage',
    sa.Column('service_id', sa.UUID(), nullable=False),
    sa.Column('api_key_id', sa.UUID(), nullable=False),
    sa.Column('usage_timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('endpoint', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], ),
    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
    sa.PrimaryKeyConstraint('service_id', 'api_key_id',  'endpoint', 'usage_timestamp')
    )
    op.create_index('ix_service_api_key_usage_timestamp', 'api_key_usage', ['service_id', 'api_key_id',
                                                                            'usage_timestamp'], unique=False)


def downgrade():
    op.drop_index('ix_service_api_key_usage_timestamp', table_name='api_key_usage')
    op.drop_table('api_key_usage')
