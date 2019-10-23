"""
Remove loadtesting provider

Revision ID: 0308_delete_loadtesting_provider
Revises: 0307_delete_dm_datetime
Create Date: 2019-10-22 17:30

"""
import uuid
from alembic import op
from sqlalchemy.sql import text

revision = '0308_delete_loadtesting_provider'
down_revision = '0307_delete_dm_datetime'


def upgrade():
    conn = op.get_bind()
    conn.execute("DELETE FROM provider_details WHERE identifier = 'loadtesting'")
    conn.execute("DELETE FROM provider_details_history WHERE identifier = 'loadtesting'")


def downgrade():
    conn = op.get_bind()
    conn.execute(
        text("""
        INSERT INTO
        provider_details
        (id, display_name, identifier, priority, notification_type, active, version, supports_international)
        VALUES
        (:uuid, 'Loadtesting', 'loadtesting', 100, 'sms', true, 1, false);
        INSERT INTO
        provider_details_history
        (id, display_name, identifier, priority, notification_type, active, version, supports_international)
        VALUES
        (:uuid, 'Loadtesting', 'loadtesting', 100, 'sms', true, 1, false)
        """),
        uuid=uuid.uuid4()
    )
