"""

Revision ID: 0183_alter_primary_key
Revises: 0182_add_upload_document_perm
Create Date: 2018-03-25 21:23:32.403212

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0183_alter_primary_key'
down_revision = '0182_add_upload_document_perm'


def upgrade():
    # Drop the old dm_datetime table and create a new one
    op.execute(
        """
        delete from dm_datetime where 1=1;
        """)

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
        (datum + TIME '00:00:00') at Time zone 'Europe/London' at TIME zone 'utc' as utc_daytime_start,	-- convert bst time to utc time
        (datum + TIME '24:00:00') at Time zone 'Europe/London' at TIME zone 'utc' as utc_daytime_end
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

    op.drop_constraint('ft_billing_pkey', 'ft_billing', type_='primary')

    op.create_primary_key('ft_billing_pkey', 'ft_billing', ['bst_date',
                                                            'template_id',
                                                            'service_id',
                                                            'rate_multiplier',
                                                            'provider',
                                                            'notification_type'])


def downgrade():
    # We do not downgrade populated data
    op.drop_constraint('ft_billing_pkey', 'ft_billing', type_='primary')

    op.create_primary_key('ft_billing_pkey', 'ft_billing', ['bst_date',
                                                            'template_id',
                                                            'rate_multiplier',
                                                            'provider',
                                                            'notification_type'])

