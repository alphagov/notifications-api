"""
Create Date: 2024-12-28 23:00:28.439436
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0485_add_job_status_fin_allrws"
down_revision = "0484_rm_daily_sorted_letter"


def upgrade():
    op.execute("INSERT INTO job_status VALUES('finished all notifications created')")


def downgrade():
    op.execute("UPDATE jobs SET job_status = 'finished' WHERE job_status = 'finished all notifications created'")
    op.execute("DELETE FROM job_status WHERE name = 'finished all notifications created'")
