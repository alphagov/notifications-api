"""

Revision ID: 0311_populate_returned_letters
Revises: 0310_returned_letters_table
Create Date: 2019-12-09 12:13:49.432993

"""
from alembic import op

from app.dao.returned_letters_dao import insert_or_update_returned_letters

revision = '0311_populate_returned_letters'
down_revision = '0310_returned_letters_table'


def upgrade():
    conn = op.get_bind()
    sql = """
        select id, service_id, reference 
        from notification_history 
        where notification_type = 'letter'
        and notification_status = 'returned-letter'"""
    results = conn.execute(sql)
    returned_letters = results.fetchall()
    references = [x.reference for x in returned_letters]
    insert_or_update_returned_letters(references)


def downgrade():
    pass
