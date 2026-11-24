"""

Create Date: 2026-11-24 09:30:00.000000
Revision ID: 0592_letter_rates_from_7_12_26
Revises: 0591_drop_replication_slot

"""

revision = "0592_letter_rates_from_7_12_26"
down_revision = "0591_drop_replication_slot"

import uuid
from datetime import datetime

from alembic import op
from sqlalchemy import text

# Server time is UTC, and the UK is on GMT in December, so this is 00:00 on the 7th December in UK time.
RATE_CHANGE_DATE = datetime(2026, 12, 7, 0, 0)

NEW_RATES = [
    # economy
    (1, 0.756, "economy"),
    (2, 0.802, "economy"),
    (3, 0.843, "economy"),
    (4, 0.897, "economy"),
    (5, 0.942, "economy"),
    # second class
    (1, 0.827, "second"),
    (2, 0.874, "second"),
    (3, 0.914, "second"),
    (4, 0.969, "second"),
    (5, 1.013, "second"),
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
            AND post_class IN ('economy', 'second')
            """
        ),
        {"end_date": RATE_CHANGE_DATE},
    )

    for crown in [True, False]:
        for sheet_count, rate, post_class in NEW_RATES:
            conn.execute(
                text(
                    """
                    INSERT INTO letter_rates (id, start_date, sheet_count, rate, crown, post_class)
                        VALUES (:id, :start_date, :sheet_count, :rate, :crown, :post_class)
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "start_date": RATE_CHANGE_DATE,
                    "sheet_count": sheet_count,
                    "rate": rate,
                    "crown": crown,
                    "post_class": post_class,
                }
            )


def downgrade():
    conn = op.get_bind()
    # remove new rates
    conn.execute(
        text(
            """
            DELETE FROM letter_rates
            WHERE start_date = :start_date
            AND post_class IN ('economy', 'second')
            """
        ),
        {"start_date": RATE_CHANGE_DATE},
    )
    # make old rates active again
    conn.execute(
        text(
            """
            UPDATE letter_rates
            SET end_date = null
            WHERE end_date = :end_date
            AND post_class IN ('economy', 'second')
            """
        ),
        {"end_date": RATE_CHANGE_DATE},
    )
