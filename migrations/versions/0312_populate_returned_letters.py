"""

Revision ID: 0312_populate_returned_letters
Revises: 0311_add_inbound_sms_history
Create Date: 2019-12-09 12:13:49.432993

"""
from alembic import op

revision = '0312_populate_returned_letters'
down_revision = '0311_add_inbound_sms_history'


def upgrade():
    conn = op.get_bind()
    sql = """
        select id, service_id, reference, updated_at
        from notification_history 
        where notification_type = 'letter'
        and notification_status = 'returned-letter'"""
    insert_sql = """
        insert into returned_letters(id, reported_at, service_id, notification_id, created_at, updated_at) 
        values(uuid_in(md5(random()::text)::cstring), '{}', '{}', '{}', now(), null)
    """

    results = conn.execute(sql)
    returned_letters = results.fetchall()
    for x in returned_letters:
        f = insert_sql.format(x.updated_at.date(), x.service_id, x.id)
        conn.execute(f)


def downgrade():
    pass
