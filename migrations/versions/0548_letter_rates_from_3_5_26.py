"""

Create Date: 2026-04-13 04:00:11.329567
Revision ID: 0548_letter_rates_from_3_5_26
Revises: 0547_new_sms_allowance_n_rate

"""

revision = "0548_letter_rates_from_3_5_26"
down_revision = "0547_new_sms_allowance_n_rate"

import uuid
from datetime import datetime

from alembic import op
from sqlalchemy import text

# Server time is UTC, so 23:00 UTC on 2 May 2026, which is 00:00 BST on 3 May 2026.
RATE_CHANGE_DATE = datetime(2026, 5, 2, 23, 0)

NEW_RATES = [
    # europe
    (RATE_CHANGE_DATE, 1, 1.80, "europe"),
    (RATE_CHANGE_DATE, 2, 1.84, "europe"),
    (RATE_CHANGE_DATE, 3, 1.88, "europe"),
    (RATE_CHANGE_DATE, 4, 1.92, "europe"),
    (RATE_CHANGE_DATE, 5, 1.96, "europe"),
    # rest of the world
    (RATE_CHANGE_DATE, 1, 1.80, "rest-of-world"),
    (RATE_CHANGE_DATE, 2, 1.84, "rest-of-world"),
    (RATE_CHANGE_DATE, 3, 1.88, "rest-of-world"),
    (RATE_CHANGE_DATE, 4, 1.92, "rest-of-world"),
    (RATE_CHANGE_DATE, 5, 1.96, "rest-of-world"),
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
                post_class IN ('europe','rest-of-world')
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
            DELETE FROM
                letter_rates
            WHERE
                start_date = :start_date
            AND
                post_class IN ('europe','rest-of-world')
            """
        ),
        { "start_date": RATE_CHANGE_DATE },
    )

    conn.execute(
        text(
            """
            UPDATE
                letter_rates
            SET
                end_date = null
            WHERE
                end_date = :end_date
            AND
                post_class IN ('europe','rest-of-world')
            """
        ),
        { "end_date": RATE_CHANGE_DATE },
    )
