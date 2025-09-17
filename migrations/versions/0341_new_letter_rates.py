"""

Revision ID: 0341_new_letter_rates
Revises: 0340_stub_training_broadcasts
Create Date: 2021-01-27 11:58:21.393227

"""

import itertools
import uuid
from datetime import datetime

from alembic import op
from sqlalchemy.sql import text

from app.models import LetterRate

revision = "0341_new_letter_rates"
down_revision = "0340_stub_training_broadcasts"


CHANGEOVER_DATE = datetime(2021, 2, 1, 0, 0)


def get_new_rate(sheet_count, post_class):
    base_prices = {
        "second": 34,
        "first": 64,
        "europe": 81,
        "rest-of-world": 81,
    }
    multiplier = 5 if post_class in ("first", "second") else 8

    return (base_prices[post_class] + (multiplier * sheet_count)) / 100.0


def upgrade():
    conn = op.get_bind()
    conn.execute(text("UPDATE letter_rates SET end_date = :start WHERE end_date IS NULL"), start=CHANGEOVER_DATE)

    op.bulk_insert(
        LetterRate.__table__,
        [
            {
                "id": uuid.uuid4(),
                "start_date": CHANGEOVER_DATE,
                "end_date": None,
                "sheet_count": sheet_count,
                "rate": get_new_rate(sheet_count, post_class),
                "crown": crown,
                "post_class": post_class,
            }
            for sheet_count, crown, post_class in itertools.product(
                range(1, 6), [True, False], ["first", "second", "europe", "rest-of-world"]
            )
        ],
    )


def downgrade():
    # Make sure you've thought about billing implications etc before downgrading!
    conn = op.get_bind()
    conn.execute(text("DELETE FROM letter_rates WHERE start_date = :start"), start=CHANGEOVER_DATE)
    conn.execute(text("UPDATE letter_rates SET end_date = NULL WHERE end_date = :start"), start=CHANGEOVER_DATE)
