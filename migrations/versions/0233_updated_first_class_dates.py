"""empty message

Revision ID: 0233_updated_first_class_dates
Revises: 0230_noti_postage_constraint_3

"""

revision = '0233_updated_first_class_dates'
down_revision = '0230_noti_postage_constraint_3'

from datetime import datetime
from alembic import op
from sqlalchemy.sql import text


START_DATE = datetime(2018, 8, 31, 23, 0)


def upgrade():
    conn = op.get_bind()
    conn.execute(text(
        """UPDATE letter_rates SET start_date = :start_date WHERE post_class = 'first'"""
    ), start_date=START_DATE)


def downgrade():
    '''
    This data migration should not be downgraded. Downgrading may cause billing errors
    and the /montly-usage endpoint to stop working.
    '''
