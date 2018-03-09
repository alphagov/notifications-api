"""

Revision ID: 0174_add_billing_facts
Revises: 0173_create_daily_sorted_letter
Create Date: 2018-03-07 12:21:53.098887

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0174_add_billing_facts'
down_revision = '0173_create_daily_sorted_letter'


def upgrade():
    # Create notifications_for_today table
    op.create_table('ft_billing',
                    sa.Column('bst_date', sa.Date(), nullable=True),
                    sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=True),
                    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=True),
                    sa.Column('organisation_id', postgresql.UUID(as_uuid=True), nullable=True),
                    sa.Column('annual_billing_id', postgresql.UUID(as_uuid=True), nullable=True),
                    sa.Column('notification_type', sa.Text(), nullable=True),
                    sa.Column('provider', sa.Text(), nullable=True),
                    sa.Column('crown', sa.Text(), nullable=True),
                    sa.Column('rate_multiplier', sa.Numeric(), nullable=True),
                    sa.Column('international', sa.Boolean(), nullable=True),
                    sa.Column('rate', sa.Numeric(), nullable=True),
                    sa.Column('billable_units', sa.Numeric(), nullable=True),
                    sa.Column('notifications_sent', sa.Integer(), nullable=True),
                    sa.PrimaryKeyConstraint('bst_date', 'template_id')
                    )
    # Set indexes
    op.create_index(op.f('ix_ft_billing_bst_date'), 'ft_billing', ['bst_date'], unique=False)
    op.create_index(op.f('ix_ft_billing_service_id'), 'ft_billing', ['service_id'], unique=False)

    # Create dm_datetime table
    op.create_table('dm_datetime',
                    sa.Column('bst_date', sa.Date(), nullable=False),
                    sa.Column('year', sa.Integer(), nullable=False),
                    sa.Column('month', sa.Integer(), nullable=False),
                    sa.Column('month_name', sa.String(), nullable=False),
                    sa.Column('day', sa.Integer(), nullable=True),
                    sa.Column('bst_day', sa.Integer(), nullable=False),
                    sa.Column('day_of_year', sa.Integer(), nullable=False),
                    sa.Column('week_day_name', sa.String(), nullable=False),
                    sa.Column('calendar_week', sa.Integer(), nullable=True),
                    sa.Column('quartal', sa.String(), nullable=False),
                    sa.Column('year_quartal', sa.String(), nullable=False),
                    sa.Column('year_month', sa.String(), nullable=False),
                    sa.Column('year_calendar_week', sa.String(), nullable=False),
                    sa.Column('financial_year', sa.Integer(), nullable=True),
                    sa.Column('utc_daytime_start', sa.DateTime(), nullable=False),
                    sa.Column('utc_daytime_end', sa.DateTime(), nullable=False),
                    sa.PrimaryKeyConstraint('bst_date')
                    )
    # Set indexes
    op.create_index(op.f('ix_dm_datetime_yearmonth'), 'dm_datetime', ['year', 'month'], unique=False)
    op.create_index(op.f('ix_dm_datetime_bst_date'), 'dm_datetime', ['bst_date'], unique=False)

    # Insert data into table
    op.execute(
        """
        INSERT into dm_datetime (
        SELECT
        datum AS bst_date,
        EXTRACT(YEAR FROM datum) AS year,
        EXTRACT(MONTH FROM datum) AS month,
        -- Localized month name
        to_char(datum, 'TMMonth') AS month_name,
        EXTRACT(DAY FROM datum) AS day,
        EXTRACT(DAY FROM datum) AS bst_day,
        EXTRACT(DOY FROM datum) AS day_of_year,
        -- Localized weekday
        to_char(datum, 'TMDay') AS week_day_name,
        -- ISO calendar week
        EXTRACT(week FROM datum) AS calendar_week,
        'Q' || to_char(datum, 'Q') AS quartal,
        to_char(datum, 'yyyy/"Q"Q') AS year_quartal,
        to_char(datum, 'yyyy/mm') AS year_month,
        -- ISO calendar year and week
        to_char(datum, 'iyyy/IW') AS year_calendar_week,
        (SELECT CASE WHEN (extract(month from datum) <= 3) THEN (extract(year FROM datum) -1)
        ELSE (extract(year FROM datum)) end),
        (datum + TIME '00:00:00') at TIME zone 'utc' as utc_daytime_start,	-- convert bst time to utc time
        (datum + TIME '23:59:59') at TIME zone 'utc' as utc_daytime_end
        FROM (
        -- There are 10 leap years in this range, so calculate 365 * 50 + 5 records
        SELECT '2015-01-01'::date + SEQUENCE.DAY AS datum
        FROM generate_series(0,365*50+10) AS SEQUENCE(DAY)
        GROUP BY SEQUENCE.day
        ) DQ
        ORDER BY bst_date
        );
        """
    )


def downgrade():
    op.drop_table('ft_billing')
    op.drop_table('dm_datetime')
