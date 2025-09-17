"""
Create Date: 2025-03-26 13:37:41.828494
"""

import uuid
from datetime import datetime

from alembic import op
from sqlalchemy.sql import text

revision = '0491_letter_rates_april_2025'
down_revision = '0490_create_report_requests'


RATE_CHANGE_DATE = datetime(2025, 3, 31, 23, 0)

NEW_RATES = [
    # second class
    (1, 0.68, "second"),
    (2, 0.72, "second"),
    (3, 0.77, "second"),
    (4, 0.82, "second"),
    (5, 0.86, "second"),
    # first class
    (1, 1.49, "first"),
    (2, 1.53, "first"),
    (3, 1.57, "first"),
    (4, 1.63, "first"),
    (5, 1.67, "first"),
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
        AND post_class IN ('first', 'second')
    """
        ),
        end_date=RATE_CHANGE_DATE,
    )

    for crown in [True, False]:
        for sheet_count, rate, post_class in NEW_RATES:
            id = uuid.uuid4()
            conn.execute(
                text(
                    """
                INSERT INTO letter_rates (id, start_date, sheet_count, rate, crown, post_class)
                    VALUES (:id, :start_date, :sheet_count, :rate, :crown, :post_class)
            """
                ),
                id=id,
                start_date=RATE_CHANGE_DATE,
                sheet_count=sheet_count,
                rate=rate,
                crown=crown,
                post_class=post_class,
            )


def downgrade():
    conn = op.get_bind()
    # remove new rates
    conn.execute(
        text(
            """
            DELETE FROM letter_rates WHERE start_date = :start_date
            """
        ),
        start_date=RATE_CHANGE_DATE,
    )
    # make old rates active again
    conn.execute(
        text(
            """
            UPDATE letter_rates
            SET end_date = null
            WHERE end_date = :end_date
             """
        ),
        end_date=RATE_CHANGE_DATE,
    )
