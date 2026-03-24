"""

Create Date: 2026-03-24 16:13:11.329567
Revision ID: 0546_letter_rates_from_7_4_26
Revises: 0545_add_pending_column

"""

revision = "0546_letter_rates_from_7_4_26"
down_revision = "0545_add_pending_column"

import uuid
from datetime import datetime

from alembic import op
from sqlalchemy import text

# Server time is UTC, so this is 00:00 on the 7th April in UK time
RATE_CHANGE_DATE = datetime(2026, 4, 6, 23, 0)

NEW_RATES = [
    # first class
    (RATE_CHANGE_DATE, 1, 1.56, "first"),
    (RATE_CHANGE_DATE, 2, 1.61, "first"),
    (RATE_CHANGE_DATE, 3, 1.66, "first"),
    (RATE_CHANGE_DATE, 4, 1.71, "first"),
    (RATE_CHANGE_DATE, 5, 1.76, "first"),
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
                post_class IN ('first')
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
