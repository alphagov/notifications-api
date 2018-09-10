"""

Revision ID: 0224_returned_letter_status
Revises: 0223_add_domain_constraint
Create Date: 2018-08-21 14:44:04.203480

"""
from alembic import op


revision = '0224_returned_letter_status'
down_revision = '0223_add_domain_constraint'


def upgrade():
    op.execute("INSERT INTO notification_status_types (name) VALUES ('returned-letter')")


def downgrade():
    op.execute("DELETE FROM notification_status_types WHERE name='returned-letter'")
