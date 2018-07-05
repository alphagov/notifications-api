"""empty message

Revision ID: 0202_new_letter_pricing
Revises: 0201_another_letter_org
Create Date: 2017-07-09 12:44:16.815039

"""

revision = '0202_new_letter_pricing'
down_revision = '0201_another_letter_org'

import uuid
from datetime import datetime
from alembic import op


start = datetime(2018, 6, 30, 23, 0)

NEW_RATES = [
    (uuid.uuid4(), start, 4, 0.39, True, 'second'),
    (uuid.uuid4(), start, 4, 0.51, False, 'second'),
    (uuid.uuid4(), start, 5, 0.42, True, 'second'),
    (uuid.uuid4(), start, 5, 0.57, False, 'second'),
]


def upgrade():
    conn = op.get_bind()
    for id, start_date, sheet_count, rate, crown, post_class in NEW_RATES:
        conn.execute("""
            INSERT INTO letter_rates (id, start_date, sheet_count, rate, crown, post_class)
                VALUES ('{}', '{}', '{}', '{}', '{}', '{}')
        """.format(id, start_date, sheet_count, rate, crown, post_class))


def downgrade():
    pass
