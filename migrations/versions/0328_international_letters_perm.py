"""

Revision ID: 0328_international_letters_perm
Revises: 0327_idx_notification_history
Create Date: 2020-08-10 14:12:02.870838

"""
from alembic import op
from sqlalchemy import text

revision = '0328_international_letters_perm'
down_revision = '0327_idx_notification_history'


def upgrade():
    sql = """
        SELECT distinct(service_id) service_id
        FROM service_permissions
        WHERE service_id not in (SELECT service_id FROM service_permissions WHERE permission = 'international_letters')
    """
    insert_sql = """
        INSERT INTO service_permissions(service_id, permission, created_at)
        VALUES (:service_id, 'international_letters', now())
    """
    conn = op.get_bind()
    results = conn.execute(sql)
    services_to_add_permission = results.fetchall()
    for x in services_to_add_permission:
        conn.execute(text(insert_sql), service_id=x.service_id)


def downgrade():
    pass
