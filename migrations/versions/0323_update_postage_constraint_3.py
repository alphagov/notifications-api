"""

Revision ID: 0323_update_postage_constraint_3
Revises: 0322_update_postage_constraint_2
Create Date: 2020-03-12 12:01:41.533192

"""
from alembic import op
import sqlalchemy as sa


revision = '0323_update_postage_constraint_3'
down_revision = '0322_update_postage_constraint_2'


def upgrade():
    op.execute('ALTER TABLE notifications VALIDATE CONSTRAINT "chk_notifications_postage_null"')
    op.execute('ALTER TABLE templates VALIDATE CONSTRAINT "chk_templates_postage"')
    op.execute('ALTER TABLE templates_history VALIDATE CONSTRAINT "chk_templates_history_postage"')


def downgrade():
    pass
