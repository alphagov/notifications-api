from datetime import datetime

from app.dao.letter_rate_dao import dao_get_letter_rates_for_timestamp
from app.dao.sms_rate_dao import dao_get_sms_rate_for_timestamp
from tests.app.db import create_letter_rate, create_rate


def test_dao_get_sms_rate_for_timestamp(notify_db_session):
    # create a rate valid from 01.06
    create_rate(start_date=datetime(2024, 6, 1), value=0.0221, notification_type="sms")
    # create a rate valid from 02.06
    expected_rate = create_rate(start_date=datetime(2024, 6, 2), value=0.0227, notification_type="sms")
    # create a rate valid from 05.06
    create_rate(start_date=datetime(2024, 6, 5), value=0.03, notification_type="sms")

    # look for rate valid on 04.06
    rate = dao_get_sms_rate_for_timestamp(datetime(2024, 6, 4))
    # assert the right rate is returned
    assert rate == expected_rate


def test_dao_get_letter_rates_for_timestamp(notify_db_session):
    # create letter rates valid from 01.06
    create_letter_rate(
        start_date=datetime(2024, 6, 1), rate=0.76, post_class="first", sheet_count=3, end_date=datetime(2024, 6, 2)
    )
    create_letter_rate(
        start_date=datetime(2024, 6, 1), rate=0.45, post_class="second", sheet_count=3, end_date=datetime(2024, 6, 2)
    )
    # create letter rates valid from 02.06
    expected_rates = [
        create_letter_rate(
            start_date=datetime(2024, 6, 2), rate=0.80, post_class="first", sheet_count=3, end_date=datetime(2024, 6, 5)
        ),
        create_letter_rate(
            start_date=datetime(2024, 6, 2),
            rate=0.49,
            post_class="second",
            sheet_count=3,
            end_date=datetime(2024, 6, 5),
        ),
    ]
    # create letter rates valid from 05.06
    create_letter_rate(start_date=datetime(2024, 6, 5), rate=0.83, post_class="first", sheet_count=3)
    create_letter_rate(start_date=datetime(2024, 6, 5), rate=0.52, post_class="second", sheet_count=3)

    # look for letter rates valid on 04.06
    rates = dao_get_letter_rates_for_timestamp(datetime(2024, 6, 4))
    # assert the right letter rates are returned
    assert set(rates) == set(expected_rates)
