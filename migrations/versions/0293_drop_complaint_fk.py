"""

Revision ID: 0293_drop_complaint_fk
Revises: 0292_give_users_folder_perms
Create Date: 2019-05-16 14:05:18.104274

"""
from alembic import op


revision = '0293_drop_complaint_fk'
down_revision = '0292_give_users_folder_perms'


def upgrade():
    op.drop_constraint('complaints_notification_id_fkey', table_name='complaints', type_='foreignkey')


def downgrade():
    op.create_foreign_key('complaints_notification_id_fkey', 'complaints',
                          'notification_history', ['notification_id'], ['id'])
