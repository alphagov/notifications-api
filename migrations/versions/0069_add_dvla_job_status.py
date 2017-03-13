"""empty message

Revision ID: 0069_add_dvla_job_status
Revises: 0068_add_created_by_to_provider
Create Date: 2017-03-10 16:15:22.153948

"""

# revision identifiers, used by Alembic.
revision = '0069_add_dvla_job_status'
down_revision = '0068_add_created_by_to_provider'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute("INSERT INTO JOB_STATUS VALUES('ready to send')")
    op.execute("INSERT INTO JOB_STATUS VALUES('sent to dvla')")


def downgrade():
    op.execute("DELETE FROM JOB_STATUS WHERE name = 'ready to send'")
    op.execute("DELETE FROM JOB_STATUS where name = 'sent to dvla'")