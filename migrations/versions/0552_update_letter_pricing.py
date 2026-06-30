"""
Create Date: 2026-06-30T12:11:00
"""

import uuid
from datetime import datetime

from alembic import op
from sqlalchemy import text

revision = "0552_update_letter_pricing"
down_revision = "0551_drop_ntfcns_failed_idx"

RATE_CHANGE_DATE = datetime(2026, 6, 30, 23, 0)

NEW_RATES = [
    # economy
    (RATE_CHANGE_DATE, 1, 0.638, "economy"),
    (RATE_CHANGE_DATE, 2, 0.684, "economy"),
    (RATE_CHANGE_DATE, 3, 0.724, "economy"),
    (RATE_CHANGE_DATE, 4, 0.779, "economy"),
    (RATE_CHANGE_DATE, 5, 0.823, "economy"),
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
                post_class IN ('economy')
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
