"""empty message

Revision ID: set_notifications_international
Revises: 0080_fix_rate_start_date
Create Date: 2017-05-05 15:26:34.621670

"""

# revision identifiers, used by Alembic.
from datetime import datetime

revision = 'set_notifications_international'
down_revision = '0080_fix_rate_start_date'

from alembic import op
import sqlalchemy as sa


def upgrade():
    conn = op.get_bind()
    start = datetime.utcnow()
    all_notifications = "select id from notifications where international is null limit 1000"

    results = conn.execute(all_notifications)
    res = results.fetchall()
    while len(res) > 0:
        conn.execute("update notifications set international = False where id in ({})".format(all_notifications))
        conn.execute("update notification_history set international = False where id in ({})".format(all_notifications))
        conn.commit()
        results = conn.execute(all_notifications)
        res = results.fetchall()
    end = datetime.utcnow()
    print("Started at: {}   ended at: {}".format(start, end))

def downgrade():
    # There is no way to downgrade this update.
    pass