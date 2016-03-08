"""empty message

Revision ID: 0035_default_sent_count
Revises: 0034_job_sent_count
Create Date: 2016-03-08 09:08:55.721654

"""

# revision identifiers, used by Alembic.
revision = '0035_default_sent_count'
down_revision = '0034_job_sent_count'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute('update jobs set notifications_sent = notification_count')
    op.alter_column('jobs', 'notifications_sent',
               existing_type=sa.INTEGER(),
               nullable=False)


def downgrade():
    op.alter_column('jobs', 'notifications_sent',
               existing_type=sa.INTEGER(),
               nullable=True)
