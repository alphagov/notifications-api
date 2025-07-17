"""

Revision ID: 0439_intl_letters_jan_24
Revises: 0438_request_invite_templates
Create Date: 2024-01-02 12:39:29.779099

"""

revision = "0439_intl_letters_jan_24"
down_revision = "0438_request_invite_templates"

import itertools
import uuid
from datetime import datetime

from alembic import op
from sqlalchemy.sql import text

RATE_CHANGE_DATE = datetime(2024, 1, 2, 0, 0)

NEW_INTERNATIONAL_RATES = [
    (1, 1.44),
    (2, 1.49),
    (3, 1.53),
    (4, 1.58),
    (5, 1.63),
]


def upgrade():
    conn = op.get_bind()

    # mark old rates as inactive
    conn.execute(
        text(
            """
            UPDATE letter_rates
            SET end_date = :end_date
            WHERE end_date IS NULL
            AND post_class IN ('europe', 'rest-of-world')
            """
        ),
        {"end_date": RATE_CHANGE_DATE},
    )
    # add correct new rates
    for sheet_count, rate in NEW_INTERNATIONAL_RATES:
        for crown, post_class in itertools.product([True, False], ["europe", "rest-of-world"]):
            id = uuid.uuid4()
            conn.execute(
                text(
                    """
                    INSERT INTO letter_rates
                        (id, start_date, sheet_count, rate, crown, post_class)
                    VALUES
                        (:id, :start_date, :sheet_count, :rate, :crown, :post_class)
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
