"""

Revision ID: 0221_returned_letter_status
Revises: 0220_email_brand_type_non_null
Create Date: 2018-08-21 14:44:04.203480

"""
from alembic import op


revision = '0221_returned_letter_status'
down_revision = '0220_email_brand_type_non_null'


def upgrade():
    op.execute("INSERT INTO notification_status_types (name) VALUES ('returned-letter')")


def downgrade():
    op.execute("DELETE FROM notification_status_types WHERE name='returned-letter'")
