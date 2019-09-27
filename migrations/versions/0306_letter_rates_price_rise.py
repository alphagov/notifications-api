"""
All prices going up 5p

1 sheet (double-sided) increases from 30p to 35p (plus VAT)
2 sheets (double-sided) increases from 35p to 40p (plus VAT)
3 sheets (double-sided) increases from 40p to 45p (plus VAT)
4 sheets (double-sided) increases from 45p to 50p (plus VAT)
5 sheets (double-sided) increases from 50p to 55p (plus VAT)
First class letters:

1 sheet (double-sided) increases from 56p to 61p (plus VAT)
2 sheets (double-sided) increases from 61p to 66p (plus VAT)
3 sheets (double-sided) increases from 66p to 71p (plus VAT)
4 sheets (double-sided) increases from 71p to 76p (plus VAT)
5 sheets (double-sided) increases from 76p to 81p (plus VAT)

Revision ID: 0306_letter_rates_price_rise
Revises: 0305_add_gp_org_type
Create Date: 2019-09-25 15:43:09.388251

"""
import itertools
import uuid
from datetime import datetime

from alembic import op
from sqlalchemy.sql import text

from app.models import LetterRate


revision = '0306_letter_rates_price_rise'
down_revision = '0305_add_gp_org_type'


CHANGEOVER_DATE = datetime(2019, 9, 30, 23, 0)


def upgrade():
    # all old rates are going in the bin
    conn = op.get_bind()
    conn.execute(text("UPDATE letter_rates SET end_date = :start WHERE end_date IS NULL"), start=CHANGEOVER_DATE)

    base_prices = {
        'second': 30,
        'first': 56,
    }
    op.bulk_insert(LetterRate.__table__, [
        {
            'id': uuid.uuid4(),
            'start_date': CHANGEOVER_DATE,
            'end_date': None,
            'sheet_count': sheet_count,
            'rate': (base_prices[post_class] + (5 * sheet_count)) / 100.0,
            'crown': crown,
            'post_class': post_class,
        }
        for sheet_count, crown, post_class in itertools.product(
            range(1, 6),
            [True, False],
            ['first', 'second']
        )
    ])


def downgrade():
    # Make sure you've thought about billing implications etc before downgrading!
    conn = op.get_bind()
    conn.execute(text("DELETE FROM letter_rates WHERE start_date = :start"), start=CHANGEOVER_DATE)
    conn.execute(text("UPDATE letter_rates SET end_date = NULL WHERE end_date = :start"), start=CHANGEOVER_DATE)
