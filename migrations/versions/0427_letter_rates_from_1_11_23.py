"""

Revision ID: 0427_letter_rates_from_1_11_23
Revises: 0426_drop_email_from

"""

revision = "0427_letter_rates_from_1_11_23"
down_revision = "0426_drop_email_from"

import uuid
from datetime import datetime

from alembic import op
from sqlalchemy.sql import text

RATE_CHANGE_DATE = datetime(2023, 11, 1, 0, 0)

NEW_RATES = [
    # second class
    (RATE_CHANGE_DATE, 1, 0.54, "second"),
    (RATE_CHANGE_DATE, 2, 0.59, "second"),
    (RATE_CHANGE_DATE, 3, 0.63, "second"),
    (RATE_CHANGE_DATE, 4, 0.68, "second"),
    (RATE_CHANGE_DATE, 5, 0.73, "second"),
    # first class
    (RATE_CHANGE_DATE, 1, 0.71, "first"),
    (RATE_CHANGE_DATE, 2, 0.76, "first"),
    (RATE_CHANGE_DATE, 3, 0.80, "first"),
    (RATE_CHANGE_DATE, 4, 0.85, "first"),
    (RATE_CHANGE_DATE, 5, 0.90, "first"),
    # europe (same as rest of the world)
    (RATE_CHANGE_DATE, 1, 1.26, "europe"),
    (RATE_CHANGE_DATE, 2, 1.31, "europe"),
    (RATE_CHANGE_DATE, 3, 1.35, "europe"),
    (RATE_CHANGE_DATE, 4, 1.40, "europe"),
    (RATE_CHANGE_DATE, 5, 1.45, "europe"),
    # rest of the world (same as europe)
    (RATE_CHANGE_DATE, 1, 1.26, "rest-of-world"),
    (RATE_CHANGE_DATE, 2, 1.31, "rest-of-world"),
    (RATE_CHANGE_DATE, 3, 1.35, "rest-of-world"),
    (RATE_CHANGE_DATE, 4, 1.40, "rest-of-world"),
    (RATE_CHANGE_DATE, 5, 1.45, "rest-of-world"),
]


def upgrade():
    conn = op.get_bind()
    conn.execute(
        text(
            """
        UPDATE
            letter_rates
        SET
            end_date = :rate_change_date
        WHERE
            end_date IS NULL
    """
        ),
        rate_change_date=RATE_CHANGE_DATE,
    )

    for crown in [True, False]:
        for start_date, sheet_count, rate, post_class in NEW_RATES:
            id = uuid.uuid4()
            conn.execute(
                text(
                    """
                INSERT INTO letter_rates (id, start_date, sheet_count, rate, crown, post_class)
                    VALUES (:id, :start_date, :sheet_count, :rate, :crown, :post_class)
            """
                ),
                id=id,
                start_date=start_date,
                sheet_count=sheet_count,
                rate=rate,
                crown=crown,
                post_class=post_class,
            )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        text(
            """
        delete from
            letter_rates
        where
            start_date = :rate_change_date
    """
        ),
        rate_change_date=RATE_CHANGE_DATE,
    )

    conn.execute(
        text(
            """
        update
            letter_rates
        set
            end_date = null
        where
            end_date = :rate_change_date
    """
        ),
        rate_change_date=RATE_CHANGE_DATE,
    )
