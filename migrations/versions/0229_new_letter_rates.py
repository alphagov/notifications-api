"""empty message

Revision ID: 0229_new_letter_rates
Revises: 0228_notification_postage

"""

revision = '0229_new_letter_rates'
down_revision = '0228_notification_postage'

import uuid
from datetime import datetime
from alembic import op
from sqlalchemy.sql import text



START = datetime(2018, 9, 30, 23, 0)

NEW_RATES = [
    (uuid.uuid4(), START, 1, 0.30, False, 'second'),
    (uuid.uuid4(), START, 2, 0.35, True, 'second'),
    (uuid.uuid4(), START, 2, 0.35, False, 'second'),
    (uuid.uuid4(), START, 3, 0.40, True, 'second'),
    (uuid.uuid4(), START, 3, 0.40, False, 'second'),
    (uuid.uuid4(), START, 4, 0.45, True, 'second'),
    (uuid.uuid4(), START, 4, 0.45, False, 'second'),
    (uuid.uuid4(), START, 5, 0.50, True, 'second'),
    (uuid.uuid4(), START, 5, 0.50, False, 'second'),
    (uuid.uuid4(), START, 1, 0.56, True, 'first'),
    (uuid.uuid4(), START, 1, 0.56, False, 'first'),
    (uuid.uuid4(), START, 2, 0.61, True, 'first'),
    (uuid.uuid4(), START, 2, 0.61, False, 'first'),
    (uuid.uuid4(), START, 3, 0.66, True, 'first'),
    (uuid.uuid4(), START, 3, 0.66, False, 'first'),
    (uuid.uuid4(), START, 4, 0.71, True, 'first'),
    (uuid.uuid4(), START, 4, 0.71, False, 'first'),
    (uuid.uuid4(), START, 5, 0.76, True, 'first'),
    (uuid.uuid4(), START, 5, 0.76, False, 'first'),
]


def upgrade():
    conn = op.get_bind()
    conn.execute(text("""
        update
            letter_rates
        set
            end_date = :start
        where
            rate != 0.30
    """), start=START)

    for id, start_date, sheet_count, rate, crown, post_class in NEW_RATES:
        conn.execute(text("""
            INSERT INTO letter_rates (id, start_date, sheet_count, rate, crown, post_class)
                VALUES (:id, :start_date, :sheet_count, :rate, :crown, :post_class)
        """), id=id, start_date=start_date, sheet_count=sheet_count, rate=rate, crown=crown, post_class=post_class)


def downgrade():
    conn = op.get_bind()
    conn.execute(text("""
        delete from
            letter_rates
        where
            start_date = :start
    """), start=START)

    conn.execute(text("""
        update
            letter_rates
        set
            end_date = null
        where
            end_date = :start
    """), start=START)
