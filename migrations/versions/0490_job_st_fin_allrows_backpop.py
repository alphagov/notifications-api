"""
Create Date: 2025-01-27 10:36:53.370957
"""

import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0490_job_st_fin_allrows_backpop"
down_revision = "0489_populate_new_billing_cols"


def upgrade():
    jobs = sa.table("jobs", sa.column("job_status", sa.String), sa.column("scheduled_for", sa.DateTime), sa.column("processing_started", sa.DateTime))
    uniform_now = datetime.datetime.utcnow()
    # the only timestamp column with an index is scheduled_for
    op.execute(
        jobs.update()
        .where(
            jobs.c.job_status == "finished",
            jobs.c.scheduled_for < uniform_now - datetime.timedelta(days=1),
        )
        .values(job_status="finished all notifications created")
    )
    # but scheduled_for is nullable, so we need to also handle the (few) rows with null values
    op.execute(
        jobs.update()
        .where(
            jobs.c.job_status == "finished",
            jobs.c.scheduled_for.is_(None),
            jobs.c.processing_started < uniform_now - datetime.timedelta(days=1),
        )
        .values(job_status="finished all notifications created")
    )


def downgrade():
    # leave 0485_add_job_status_fin_allrws' downgrade responsible for reverting all affected
    # rows to 'finished'
    pass
