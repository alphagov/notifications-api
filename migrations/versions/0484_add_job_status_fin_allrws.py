"""
Create Date: 2024-12-28 23:00:28.439436
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0484_add_job_status_fin_allrws"
down_revision = "0483_rm_ntfcn_service_composite"


def upgrade():
    op.execute("INSERT INTO job_status VALUES('finished all notifications created')")


def downgrade():
    op.execute("DELETE FROM job_status WHERE name = 'finished all notifications created'")
