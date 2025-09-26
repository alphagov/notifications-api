"""
Create Date: 2025-04-24 16:28:42.775750
"""

from alembic import op
from sqlalchemy import text 

revision = '0499_merge_callback_tables'
down_revision = '0498_join_a_service_for_all'


def upgrade():
    conn = op.get_bind()
    conn.execute(
            text(
                """
                INSERT INTO service_callback_api (id, service_id, url, bearer_token, created_at, updated_by_id,
                                                version, updated_at, callback_type)
                SELECT id, service_id, url, bearer_token, created_at, updated_by_id,version, updated_at, 'inbound_sms' 
                FROM  service_inbound_api
                ON CONFLICT DO NOTHING 
                
                """
            )
    )
    conn.execute(
            text(
                """
                INSERT INTO service_callback_api_history (id, service_id, url, bearer_token, created_at, updated_by_id,
                                                version, updated_at, callback_type)
                SELECT id, service_id, url, bearer_token, created_at, updated_by_id,version, updated_at, 'inbound_sms' 
                FROM  service_inbound_api_history
                ON CONFLICT DO NOTHING
                """
            )
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(
            text(
                """
                DELETE FROM service_callback_api WHERE callback_type='inbound_sms'
                """
            )
    )
    conn.execute(
            text(
                """
                DELETE FROM service_callback_api_history WHERE callback_type='inbound_sms'
                """
            )
    )
