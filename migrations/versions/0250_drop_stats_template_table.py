"""

Revision ID: 0250_drop_stats_template_table
Revises: 0249_another_letter_org
Create Date: 2019-01-15 16:47:08.049369

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0250_drop_stats_template_table'
down_revision = '0249_another_letter_org'


def upgrade():
    op.drop_index('ix_stats_template_usage_by_month_month', table_name='stats_template_usage_by_month')
    op.drop_index('ix_stats_template_usage_by_month_template_id', table_name='stats_template_usage_by_month')
    op.drop_index('ix_stats_template_usage_by_month_year', table_name='stats_template_usage_by_month')
    op.drop_table('stats_template_usage_by_month')


def downgrade():
    op.create_table('stats_template_usage_by_month',
                    sa.Column('template_id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.Column('month', sa.INTEGER(), autoincrement=False, nullable=False),
                    sa.Column('year', sa.INTEGER(), autoincrement=False, nullable=False),
                    sa.Column('count', sa.INTEGER(), autoincrement=False, nullable=False),
                    sa.ForeignKeyConstraint(['template_id'], ['templates.id'],
                                            name='stats_template_usage_by_month_template_id_fkey'),
                    sa.PrimaryKeyConstraint('template_id', 'month', 'year', name='stats_template_usage_by_month_pkey')
                    )
    op.create_index('ix_stats_template_usage_by_month_year', 'stats_template_usage_by_month', ['year'], unique=False)
    op.create_index('ix_stats_template_usage_by_month_template_id', 'stats_template_usage_by_month', ['template_id'],
                    unique=False)
    op.create_index('ix_stats_template_usage_by_month_month', 'stats_template_usage_by_month', ['month'], unique=False)
