"""

Revision ID: 0325_int_letter_rates_fix
Revises: 0324_int_letter_rates
Create Date: 2020-07-15 10:09:17.218183

"""
from datetime import datetime

from alembic import op
from sqlalchemy.sql import text

revision = '0325_int_letter_rates_fix'
down_revision = '0324_int_letter_rates'


old_start_date = datetime(2020, 7, 1, 0, 0)
new_start_date = datetime(2020, 6, 30, 23, 0)


def upgrade():
    conn = op.get_bind()
    conn.execute(text(
        """UPDATE letter_rates SET start_date = :new_start_date WHERE start_date = :old_start_date"""
    ), new_start_date=new_start_date, old_start_date=old_start_date)


def downgrade():
    conn = op.get_bind()
    conn.execute(text(
        """UPDATE letter_rates SET start_date = :old_start_date WHERE start_date = :new_start_date"""
    ), old_start_date=old_start_date, new_start_date=new_start_date)
