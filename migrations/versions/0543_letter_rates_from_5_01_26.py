"""

Create Date: 2025-12-17 17:07:41.828494
Revision ID: 0543_letter_rates_from_5_01_26
Revises: 0542_backfill_confirm_sender

"""

revision = "0543_letter_rates_from_5_01_26"
down_revision = "0542_backfill_confirm_sender"

import uuid
from datetime import datetime

from alembic import op
from sqlalchemy import text

RATE_CHANGE_DATE = datetime(2026, 1, 5, 0, 0)

NEW_RATES = [
    # economy
    (RATE_CHANGE_DATE, 1, 0.64, "economy"),
    (RATE_CHANGE_DATE, 2, 0.69, "economy"),
    (RATE_CHANGE_DATE, 3, 0.73, "economy"),
    (RATE_CHANGE_DATE, 4, 0.78, "economy"),
    (RATE_CHANGE_DATE, 5, 0.82, "economy"),
    # second class
    (RATE_CHANGE_DATE, 1, 0.73, "second"),
    (RATE_CHANGE_DATE, 2, 0.77, "second"),
    (RATE_CHANGE_DATE, 3, 0.82, "second"),
    (RATE_CHANGE_DATE, 4, 0.87, "second"),
    (RATE_CHANGE_DATE, 5, 0.91, "second"),
    # europe
    (RATE_CHANGE_DATE, 1, 1.72, "europe"),
    (RATE_CHANGE_DATE, 2, 1.77, "europe"),
    (RATE_CHANGE_DATE, 3, 1.82, "europe"),
    (RATE_CHANGE_DATE, 4, 1.85, "europe"),
    (RATE_CHANGE_DATE, 5, 1.90, "europe"),
    # rest of the world
    (RATE_CHANGE_DATE, 1, 1.72, "rest-of-world"),
    (RATE_CHANGE_DATE, 2, 1.77, "rest-of-world"),
    (RATE_CHANGE_DATE, 3, 1.82, "rest-of-world"),
    (RATE_CHANGE_DATE, 4, 1.85, "rest-of-world"),
    (RATE_CHANGE_DATE, 5, 1.90, "rest-of-world"),
]


def upgrade():
    conn = op.get_bind()
    conn.execute(
        text(
            """
            UPDATE
                letter_rates
            SET
                end_date = :end_date
            WHERE
                end_date IS NULL
            AND
                post_class IN ('economy', 'second', 'europe', 'rest-of-world')
            """
        ),
        { "end_date": RATE_CHANGE_DATE },
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
                {
                    "id": id,
                    "start_date": start_date,
                    "sheet_count": sheet_count,
                    "rate": rate,
                    "crown": crown,
                    "post_class": post_class,
                }
            )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        text(
            """
            delete from
                letter_rates
            where
                start_date = :start_date
            """
        ),
        { "start_date": RATE_CHANGE_DATE },
    )

    conn.execute(
        text(
            """
            update
                letter_rates
            set
                end_date = null
            where
                end_date = :end_date
            """
        ),
        { "end_date": RATE_CHANGE_DATE },
    )
