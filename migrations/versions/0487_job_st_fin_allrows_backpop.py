"""
Create Date: 2025-01-27 10:36:53.370957
"""

import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0487_job_st_fin_allrows_backpop"
down_revision = "0486_letter_rates_feb_2025"


def upgrade():
    jobs = sa.table("jobs", sa.column("job_status", sa.String), sa.column("scheduled_for", sa.DateTime))
    op.execute(
        jobs.update()
        .where(
            jobs.c.job_status == "finished",
            jobs.c.scheduled_for < datetime.datetime.utcnow() - datetime.timedelta(days=1),
        )
        .values(job_status="finished all notifications created")
    )


def downgrade():
    # leave 0485_add_job_status_fin_allrws' downgrade responsible for reverting all affected
    # rows to 'finished'
    pass
