"""empty message

Revision ID: 0106_drop_template_stats
Revises: 0105_opg_letter_org
Create Date: 2017-07-10 14:25:58.494636

"""

# revision identifiers, used by Alembic.
revision = '0106_drop_template_stats'
down_revision = '0105_opg_letter_org'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    op.drop_table('template_statistics')
    op.drop_column('service_permissions', 'updated_at')


def downgrade():
    op.add_column('service_permissions',
                  sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
    op.create_table('template_statistics',
                    sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.Column('service_id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.Column('template_id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.Column('usage_count', sa.BIGINT(), autoincrement=False, nullable=False),
                    sa.Column('day', sa.DATE(), autoincrement=False, nullable=False),
                    sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
                    sa.ForeignKeyConstraint(['service_id'], ['services.id'],
                                            name='template_statistics_service_id_fkey'),
                    sa.ForeignKeyConstraint(['template_id'], ['templates.id'],
                                            name='template_statistics_template_id_fkey'),
                    sa.PrimaryKeyConstraint('id', name='template_statistics_pkey')
                    )
