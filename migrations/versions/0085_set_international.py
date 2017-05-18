"""empty message

Revision ID: 0085_set_international
Revises: 0084_add_job_stats
Create Date: 2017-05-05 15:26:34.621670

"""
from datetime import datetime
from alembic import op

# revision identifiers, used by Alembic.
revision = '0085_set_international'
down_revision = '0084_add_job_stats'


def upgrade():
    conn = op.get_bind()
    start = datetime.utcnow()
    notification_history = "select id from notification_history where international is null limit 10000"

    results = conn.execute(notification_history)
    res = results.fetchall()

    while len(res) > 0:
        conn.execute("update notification_history set international = False where id in ({})".format(
            notification_history))
        results = conn.execute(notification_history)
        res = results.fetchall()

    notifications = "select id from notifications where international is null limit 10000"
    results2 = conn.execute(notifications)
    res2 = results2.fetchall()
    while len(res2) > 0:
        conn.execute("update notifications set international = False where id in ({})".format(notifications))

        results2 = conn.execute(notifications)
        res2 = results2.fetchall()

    end = datetime.utcnow()
    print("Started at: {}   ended at: {}, taking {}".format(start, end, end-start))


def downgrade():
    # There is no way to downgrade this update.
    pass
