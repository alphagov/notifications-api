"""

Revision ID: 0278_remove_fk_to_users
Revises: 0277_consent_to_research_null
Create Date: 2019-03-06 16:49:28.674498

"""
from alembic import op
import sqlalchemy as sa


revision = '0278_remove_fk_to_users'
down_revision = '0277_consent_to_research_null'


def upgrade():
    op.drop_constraint('notification_history_created_by_id_fkey', 'notification_history', type_='foreignkey')


def downgrade():
    op.create_foreign_key('notification_history_created_by_id_fkey', 'notification_history', 'users', ['created_by_id'], ['id'])
