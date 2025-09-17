"""

Revision ID: 0428_letter_rates_errata
Revises: 0427_letter_rates_from_1_11_23

"""

revision = "0428_letter_rates_errata"
down_revision = "0427_letter_rates_from_1_11_23"

import uuid
from datetime import datetime

from alembic import op
from sqlalchemy.sql import text

RATE_CHANGE_DATE = datetime(2023, 11, 1, 0, 0)

CORRECTED_NEW_RATES = [
    # first class
    (RATE_CHANGE_DATE, 1, 0.82, "first"),
    (RATE_CHANGE_DATE, 2, 0.86, "first"),
    (RATE_CHANGE_DATE, 3, 0.90, "first"),
    (RATE_CHANGE_DATE, 4, 0.96, "first"),
    (RATE_CHANGE_DATE, 5, 1.00, "first"),
]


def upgrade():
    conn = op.get_bind()
    # DROP the incorrect rates
    conn.execute(
        text(
            """
        DELETE FROM
            letter_rates
        WHERE
            start_date = :rate_change_date
        AND
            post_class = 'first'
    """
        ),
        rate_change_date=RATE_CHANGE_DATE,
    )

    # add correct new rates
    for crown in [True, False]:
        for start_date, sheet_count, rate, post_class in CORRECTED_NEW_RATES:
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
    pass
