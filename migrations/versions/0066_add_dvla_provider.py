"""empty message

Revision ID: 0066_add_dvla_provider
Revises: 0065_users_current_session_id
Create Date: 2017-03-02 10:32:28.984947

"""
import uuid
from datetime import datetime

revision = '0066_add_dvla_provider'
down_revision = '0065_users_current_session_id'

from alembic import op


def upgrade():
    provider_id = str(uuid.uuid4())
    op.execute(
        "INSERT INTO provider_details (id, display_name, identifier, priority, notification_type, active, version) values ('{}', 'DVLA', 'dvla', 50, 'letter', true, 1)".format(provider_id)
    )
    op.execute(
        "INSERT INTO provider_details_history (id, display_name, identifier, priority, notification_type, active, version) values ('{}', 'DVLA', 'dvla', 50, 'letter', true, 1)".format(provider_id)
    )
    op.execute("INSERT INTO provider_rates (id, valid_from, rate, provider_id) VALUES ('{}', '{}', 1.0, '{}')".format(uuid.uuid4(), datetime.utcnow(), provider_id))


def downgrade():
    op.execute("DELETE FROM provider_rates where provider_id = (SELECT id from provider_details where display_name='DVLA')")
    op.execute("DELETE FROM provider_details_history where display_name = 'DVLA'")
    op.execute("DELETE FROM provider_details where display_name = 'DVLA'")
