"""empty message

Revision ID: 0080_fix_rate_start_date
Revises: 0079_update_rates
Create Date: 2017-05-03 16:50:11.334116

"""

# revision identifiers, used by Alembic.
revision = '0080_fix_rate_start_date'
down_revision = '0079_update_rates'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.get_bind()
    op.execute("UPDATE RATES SET valid_from = '2017-03-31 23:00:00' WHERE valid_from = '2017-04-01 00:00:00'")


def downgrade():
    op.get_bind()
    op.execute("UPDATE RATES SET valid_from = '2017-03-31 23:00:00' WHERE valid_from = '2017-04-01 00:00:00'")
