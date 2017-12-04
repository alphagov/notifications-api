"""

Revision ID: 0142_validate_constraint
Revises: 0141_remove_unused
Create Date: 2017-11-15 14:39:13.657666

"""
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0142_validate_constraint'
down_revision = '0141_remove_unused'


def upgrade():
    op.execute('ALTER TABLE notifications VALIDATE CONSTRAINT "notifications_templates_history_fkey"')
    op.execute('ALTER TABLE notification_history VALIDATE CONSTRAINT "notification_history_templates_history_fkey"')


def downgrade():
    pass
