"""

Revision ID: 0323_update_postage_constraint_3
Revises: 0322_update_postage_constraint_2
Create Date: 2020-05-12 16:21:56.210025

"""
from alembic import op


revision = '0323_update_postage_constraint_3'
down_revision = '0322_update_postage_constraint_2'


def upgrade():
    op.execute('ALTER TABLE notifications VALIDATE CONSTRAINT "chk_notifications_postage_null"')
    op.execute('ALTER TABLE templates VALIDATE CONSTRAINT "chk_templates_postage"')
    op.execute('ALTER TABLE templates_history VALIDATE CONSTRAINT "chk_templates_history_postage"')


def downgrade():
    pass
