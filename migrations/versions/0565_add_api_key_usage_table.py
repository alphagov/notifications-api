"""
Create Date: 2026-09-08 13:11:02.589651
"""

from alembic import op
import sqlalchemy as sa

revision = '0565_add_api_key_usage_table'
down_revision = '0564_block_ofcom_protected'


def upgrade():
    op.create_table('api_key_usage',
    sa.Column('service_id', sa.UUID(), nullable=False),
    sa.Column('api_key_id', sa.UUID(), nullable=False),
    sa.Column('usage_hour', sa.DateTime(timezone=True), nullable=False),
    sa.Column('endpoint', sa.String(), nullable=False),

    sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], ),
    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
    sa.PrimaryKeyConstraint('service_id', 'api_key_id', 'usage_hour', 'endpoint'),
    sa.CheckConstraint("date_trunc('hour', usage_hour) = usage_hour",
                       name='ck_api_key_usage_usage_hour')
    )


def downgrade():
    op.drop_table('api_key_usage')
