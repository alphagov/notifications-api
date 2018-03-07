from datetime import date

from app.dao.daily_sorted_letter_dao import (
    dao_create_or_update_daily_sorted_letter,
    dao_get_daily_sorted_letter_by_billing_day,
)
from app.models import DailySortedLetter
from tests.app.db import create_daily_sorted_letter


def test_dao_get_daily_sorted_letter_by_billing_day(notify_db, notify_db_session):
    billing_day = date(2018, 2, 1)
    other_day = date(2017, 9, 8)

    daily_sorted_letters = create_daily_sorted_letter(billing_day=billing_day)

    assert dao_get_daily_sorted_letter_by_billing_day(billing_day) == daily_sorted_letters
    assert not dao_get_daily_sorted_letter_by_billing_day(other_day)


def test_dao_create_or_update_daily_sorted_letter_creates_a_new_entry(notify_db, notify_db_session):
    billing_day = date(2018, 2, 1)
    dsl = DailySortedLetter(billing_day=billing_day, unsorted_count=2, sorted_count=0)
    dao_create_or_update_daily_sorted_letter(dsl)

    daily_sorted_letter = dao_get_daily_sorted_letter_by_billing_day(billing_day)

    assert daily_sorted_letter.billing_day == billing_day
    assert daily_sorted_letter.unsorted_count == 2
    assert daily_sorted_letter.sorted_count == 0
    assert not daily_sorted_letter.updated_at


def test_dao_create_or_update_daily_sorted_letter_updates_an_existing_entry(
    notify_db,
    notify_db_session
):
    create_daily_sorted_letter(unsorted_count=2, sorted_count=3)

    dsl = DailySortedLetter(billing_day=date(2018, 1, 18), unsorted_count=5, sorted_count=17)
    dao_create_or_update_daily_sorted_letter(dsl)

    daily_sorted_letter = dao_get_daily_sorted_letter_by_billing_day(dsl.billing_day)

    assert daily_sorted_letter.unsorted_count == 7
    assert daily_sorted_letter.sorted_count == 20
    assert daily_sorted_letter.updated_at
