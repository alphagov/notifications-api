"""

Revision ID: 0279_remove_fk_to_users
Revises: 0278_add_more_stuff_to_orgs
Create Date: 2019-03-06 16:49:28.674498

"""
from alembic import op

revision = '0279_remove_fk_to_users'
down_revision = '0278_add_more_stuff_to_orgs'


def upgrade():
    op.drop_constraint('notification_history_created_by_id_fkey', 'notification_history', type_='foreignkey')


def downgrade():
    op.create_foreign_key('notification_history_created_by_id_fkey', 'notification_history', 'users', ['created_by_id'], ['id'])
