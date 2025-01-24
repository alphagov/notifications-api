"""
Create Date: 2025-01-24 12:05:58.010551
"""

from alembic import op

revision = '0847_returned_letter_callback'
down_revision = '0486_letter_rates_feb_2025'


def upgrade():
    insert_returned_letter_callback_type = "INSERT INTO service_callback_type VALUES ('returned_letter')"
    op.execute(insert_returned_letter_callback_type)


def downgrade():
    pass
