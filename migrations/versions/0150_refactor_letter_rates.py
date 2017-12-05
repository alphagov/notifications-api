"""

Revision ID: 0150_refactor_letter_rates
Revises: 0149_add_crown_to_services
Create Date: 2017-12-05 10:24:41.232128

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0150_refactor_letter_rates'
down_revision = '0149_add_crown_to_services'


def upgrade():
    op.drop_table('letter_rate_details')
    op.drop_table('letter_rates')
    op.create_table('letter_rates',
                    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('start_date', sa.DateTime(), nullable=False),
                    sa.Column('end_date', sa.DateTime(), nullable=True),
                    sa.Column('sheet_total', sa.Integer(), nullable=False),
                    sa.Column('rate', sa.Numeric(), nullable=False),
                    sa.Column('crown', sa.Boolean(), nullable=False),
                    sa.Column('post_class', sa.String(), nullable=False),
                    sa.PrimaryKeyConstraint('id')
                    )


def downgrade():
    op.drop_table('letter_rates')
    op.create_table('letter_rates',
                    sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.Column('valid_from', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
                    sa.PrimaryKeyConstraint('id', name='letter_rates_pkey'),
                    postgresql_ignore_search_path=False
                    )
    op.create_table('letter_rate_details',
                    sa.Column('id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.Column('letter_rate_id', postgresql.UUID(), autoincrement=False, nullable=False),
                    sa.Column('page_total', sa.INTEGER(), autoincrement=False, nullable=False),
                    sa.Column('rate', sa.NUMERIC(), autoincrement=False, nullable=False),
                    sa.ForeignKeyConstraint(['letter_rate_id'], ['letter_rates.id'],
                                            name='letter_rate_details_letter_rate_id_fkey'),
                    sa.PrimaryKeyConstraint('id', name='letter_rate_details_pkey')
                    )
