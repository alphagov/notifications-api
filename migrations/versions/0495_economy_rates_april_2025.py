"""
Create Date: 2025-04-10 17:21:32.456534
"""

import uuid
from datetime import datetime

from alembic import op
from sqlalchemy.sql import text

revision = '0495_economy_rates_april_2025'
down_revision = '0494_add_intl_sms_limit_column'


RATE_CHANGE_DATE = datetime(2025, 3, 31, 23, 0)
POST_CLASS = "economy"

NEW_RATES = [
    # economy class
    (1, 0.59),
    (2, 0.64),
    (3, 0.68),
    (4, 0.73),
    (5, 0.78),
]


def upgrade():
    conn = op.get_bind()

    for crown in [True, False]:
        for sheet_count, rate in NEW_RATES:
            rates_id = uuid.uuid4()
            conn.execute(
                text(
                    """
                INSERT INTO letter_rates (id, start_date, sheet_count, rate, crown, post_class)
                    VALUES (:id, :start_date, :sheet_count, :rate, :crown, :post_class)
            """
                ),
                id=rates_id,
                start_date=RATE_CHANGE_DATE,
                sheet_count=sheet_count,
                rate=rate,
                crown=crown,
                post_class=POST_CLASS,
            )


def downgrade():
    conn = op.get_bind()
    # remove economy rates
    conn.execute(
        text(
            """
        DELETE FROM letter_rates WHERE post_class = :post_class
    """
        ),
        post_class=POST_CLASS,
    )

