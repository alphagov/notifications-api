"""
Create Date: 2025-01-24 12:05:58.010551
"""

from alembic import op

revision = "0847_returned_letter_callback"
down_revision = "0486_letter_rates_feb_2025"


def upgrade():
    insert_returned_letter_callback_type = "INSERT INTO service_callback_type VALUES ('returned_letter')"
    op.execute(insert_returned_letter_callback_type)


def downgrade():
    delete_returned_letter_callback = "DELETE FROM service_callback_api WHERE callback_type='returned_letter'"
    delete_returned_letter_callback_history = \
        "DELETE FROM service_callback_api_history WHERE callback_type='returned_letter'"
    delete_returned_letter_callback_type = "DELETE FROM service_callback_type WHERE name='returned_letter'"

    op.execute(delete_returned_letter_callback)
    op.execute(delete_returned_letter_callback_history)
    op.execute(delete_returned_letter_callback_type)
