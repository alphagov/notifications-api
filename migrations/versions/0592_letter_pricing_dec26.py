"""
Create Date: 2026-11-25 00:00:00
"""

import uuid
from datetime import datetime

from alembic import op
from sqlalchemy import text

revision = "0592_letter_pricing_dec26"
down_revision = "0591_drop_replication_slot"

RATE_CHANGE_DATE = datetime(2026, 12, 7, 0, 0)

NEW_RATES = [
    # economy
    (RATE_CHANGE_DATE, 1, 0.741, "economy"),
    (RATE_CHANGE_DATE, 2, 0.786, "economy"),
    (RATE_CHANGE_DATE, 3, 0.826, "economy"),
    (RATE_CHANGE_DATE, 4, 0.89, "economy"),
    (RATE_CHANGE_DATE, 5, 0.925, "economy"),
    # second class
    (RATE_CHANGE_DATE, 1, 0.83, "second"),
    (RATE_CHANGE_DATE, 2, 0.88, "second"),
    (RATE_CHANGE_DATE, 3, 0.91, "second"),
    (RATE_CHANGE_DATE, 4, 0.97, "second"),
    (RATE_CHANGE_DATE, 5, 1.01, "second"),
    # europe (same as rest of the world)
    (RATE_CHANGE_DATE, 1, 0.92, "europe"),
    (RATE_CHANGE_DATE, 2, 0.96, "europe"),
    (RATE_CHANGE_DATE, 3, 0.99, "europe"),
    (RATE_CHANGE_DATE, 4, 1.05, "europe"),
    (RATE_CHANGE_DATE, 5, 1.09, "europe"),
    # rest of the world (same as europe)
    (RATE_CHANGE_DATE, 1, 0.92, "rest-of-world"),
    (RATE_CHANGE_DATE, 2, 0.96, "rest-of-world"),
    (RATE_CHANGE_DATE, 3, 0.99, "rest-of-world"),
    (RATE_CHANGE_DATE, 4, 1.05, "rest-of-world"),
    (RATE_CHANGE_DATE, 5, 1.09, "rest-of-world"),
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
        {"rate_change_date": RATE_CHANGE_DATE},
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
                    "id": uuid.uuid4(),
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
                start_date = :rate_change_date
            """
        ),
        {"rate_change_date": RATE_CHANGE_DATE},
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
        {"rate_change_date": RATE_CHANGE_DATE},
    )