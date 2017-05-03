"""empty message

Revision ID: 0079_update_rates
Revises: 0078_sent_notification_status
Create Date: 2017-05-03 12:31:20.731069

"""

# revision identifiers, used by Alembic.
revision = '0079_update_rates'
down_revision = '0078_sent_notification_status'

from alembic import op


def upgrade():
    op.get_bind()
    op.execute("UPDATE RATES SET rate = 0.0158 WHERE valid_from = '2017-04-01 00:00:00'")
    op.execute("UPDATE RATES SET rate = 0.0165 WHERE valid_from = '2016-05-18 00:00:00'")


def downgrade():
    op.get_bind()
    op.execute("UPDATE RATES SET rate = 1.58 WHERE valid_from = '2017-04-01 00:00:00'")
    op.execute("UPDATE RATES SET rate = 1.65 WHERE valid_from = '2016-05-18 00:00:00'")
