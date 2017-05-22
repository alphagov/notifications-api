"""empty message

Revision ID: 0085_update_incoming_to_inbound
Revises: 0084_add_job_stats
Create Date: 2017-05-22 10:23:43.939050

"""

# revision identifiers, used by Alembic.
revision = '0085_update_incoming_to_inbound'
down_revision = '0084_add_job_stats'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.drop_column('service_permissions', 'updated_at')
    op.execute("UPDATE service_permission_types SET name='inbound_sms' WHERE name='incoming_sms'")


def downgrade():
    op.add_column('service_permissions', sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
    op.execute("UPDATE service_permission_types SET name='incoming_sms' WHERE name='inbound_sms'")
