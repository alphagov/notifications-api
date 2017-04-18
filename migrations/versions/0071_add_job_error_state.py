"""empty message

Revision ID: 0071_add_job_error_state
Revises: 0070_fix_notify_user_email
Create Date: 2017-03-10 16:15:22.153948

"""

# revision identifiers, used by Alembic.
revision = '0071_add_job_error_state'
down_revision = '0070_fix_notify_user_email'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute("INSERT INTO JOB_STATUS VALUES('error')")


def downgrade():
    op.execute("DELETE FROM JOB_STATUS WHERE name = 'error'")
