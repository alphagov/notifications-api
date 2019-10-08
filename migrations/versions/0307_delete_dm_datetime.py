"""

Revision ID: 0307_delete_dm_datetime
Revises: 0306_letter_rates_price_rise
Create Date: 2019-10-08 10:57:54.824807

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0307_delete_dm_datetime'
down_revision = '0306_letter_rates_price_rise'


def upgrade():
    op.drop_index('ix_dm_datetime_bst_date', table_name='dm_datetime')
    op.drop_index('ix_dm_datetime_yearmonth', table_name='dm_datetime')
    op.drop_table('dm_datetime')


def downgrade():
    op.create_table('dm_datetime',
    sa.Column('bst_date', sa.DATE(), autoincrement=False, nullable=False),
    sa.Column('year', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('month', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('month_name', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('day', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('bst_day', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('day_of_year', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('week_day_name', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('calendar_week', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('quartal', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('year_quartal', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('year_month', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('year_calendar_week', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('financial_year', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('utc_daytime_start', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.Column('utc_daytime_end', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('bst_date', name='dm_datetime_pkey')
    )
    op.create_index('ix_dm_datetime_yearmonth', 'dm_datetime', ['year', 'month'], unique=False)
    op.create_index('ix_dm_datetime_bst_date', 'dm_datetime', ['bst_date'], unique=False)
