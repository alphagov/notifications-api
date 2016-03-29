"""empty message

Revision ID: 0043_add_view_activity
Revises: 0042_default_stats_to_zero
Create Date: 2016-03-29 13:46:36.219549

"""

# revision identifiers, used by Alembic.
import uuid

revision = '0043_add_view_activity'
down_revision = '0042_default_stats_to_zero'

from alembic import op


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    conn = op.get_bind()
    conn.execute('COMMIT')
    conn.execute("alter type permission_types add value IF NOT EXISTS 'view_activity'")
    user_services = conn.execute("SELECT * FROM user_to_service").fetchall()
    for user_service in user_services:
        conn.execute(
            "insert into permissions (id, service_id, user_id, created_at, permission) "
            "values('{0}', '{1}', {2}, now(), 'view_activity')".format(
                uuid.uuid4(), user_service.service_id, user_service.user_id))
    conn.execute("delete from permissions where permission = 'access_developer_docs'")
    conn.execute("delete from pg_enum where enumlabel='access_developer_docs'")
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    conn = op.get_bind()
    conn.execute("delete from permissions where permission = 'view_activity'")
    conn.execute("delete from pg_enum where enumlabel = 'view_activity'")
    conn.execute('COMMIT')
    conn.execute("alter type permission_types add value IF NOT EXISTS 'access_developer_docs'")
    manage_api_key_users = conn.execute("SELECT * FROM permissions where permission='manage_api_keys'").fetchall()
    for user_service in manage_api_key_users:
        conn.execute(
            "insert into permissions (id, service_id, user_id, created_at, permission) "
            "values('{0}', '{1}', {2}, now(), 'access_developer_docs')".format(
                uuid.uuid4(), user_service.service_id, user_service.user_id))
    ### end Alembic commands ###
