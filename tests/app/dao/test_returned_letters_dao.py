from datetime import datetime, timedelta, date

from freezegun import freeze_time

from app.dao.returned_letters_dao import (
    insert_or_update_returned_letters, get_returned_letter_summary,
    fetch_returned_letters
)
from app.models import ReturnedLetter
from tests.app.db import create_notification, create_notification_history, create_returned_letter


def test_insert_or_update_returned_letters_inserts(sample_letter_template):
    notification = create_notification(template=sample_letter_template,
                                       reference='ref1')
    history = create_notification_history(template=sample_letter_template,
                                          reference='ref2')

    assert ReturnedLetter.query.count() == 0

    insert_or_update_returned_letters(['ref1', 'ref2'])

    returned_letters = ReturnedLetter.query.all()

    assert len(returned_letters) == 2
    returned_letters_ = [x.notification_id for x in returned_letters]
    assert notification.id in returned_letters_
    assert history.id in returned_letters_


def test_insert_or_update_returned_letters_updates(sample_letter_template):
    notification = create_notification(template=sample_letter_template,
                                       reference='ref1')
    history = create_notification_history(template=sample_letter_template,
                                          reference='ref2')

    assert ReturnedLetter.query.count() == 0
    with freeze_time('2019-12-09 13:30'):
        insert_or_update_returned_letters(['ref1', 'ref2'])
        returned_letters = ReturnedLetter.query.all()
        assert len(returned_letters) == 2
        for x in returned_letters:
            assert x.reported_at == date(2019, 12, 9)
            assert x.created_at == datetime(2019, 12, 9, 13, 30)
            assert not x.updated_at
            assert x.notification_id in [notification.id, history.id]

    with freeze_time('2019-12-10 14:20'):
        insert_or_update_returned_letters(['ref1', 'ref2'])
        returned_letters = ReturnedLetter.query.all()
        assert len(returned_letters) == 2
        for x in returned_letters:
            assert x.reported_at == date(2019, 12, 10)
            assert x.created_at == datetime(2019, 12, 9, 13, 30)
            assert x.updated_at == datetime(2019, 12, 10, 14, 20)
            assert x.notification_id in [notification.id, history.id]


def test_insert_or_update_returned_letters_when_no_notification(notify_db_session):
    insert_or_update_returned_letters(['ref1'])
    assert ReturnedLetter.query.count() == 0


def test_insert_or_update_returned_letters_for_history_only(sample_letter_template):
    history_1 = create_notification_history(template=sample_letter_template,
                                            reference='ref1')
    history_2 = create_notification_history(template=sample_letter_template,
                                            reference='ref2')

    assert ReturnedLetter.query.count() == 0
    insert_or_update_returned_letters(['ref1', 'ref2'])
    returned_letters = ReturnedLetter.query.all()
    assert len(returned_letters) == 2
    for x in returned_letters:
        assert x.notification_id in [history_1.id, history_2.id]


def test_insert_or_update_returned_letters_with_duplicates_in_reference_list(sample_letter_template):
    notification_1 = create_notification(template=sample_letter_template,
                                         reference='ref1')
    notification_2 = create_notification(template=sample_letter_template,
                                         reference='ref2')

    assert ReturnedLetter.query.count() == 0
    insert_or_update_returned_letters(['ref1', 'ref2', 'ref1', 'ref2'])
    returned_letters = ReturnedLetter.query.all()
    assert len(returned_letters) == 2
    for x in returned_letters:
        assert x.notification_id in [notification_1.id, notification_2.id]


def test_get_returned_letter_summary(sample_service):
    now = datetime.utcnow()
    create_returned_letter(sample_service, reported_at=now)
    create_returned_letter(sample_service, reported_at=now)

    results = get_returned_letter_summary(sample_service.id)

    assert len(results) == 1

    assert results[0].returned_letter_count == 2
    assert results[0].reported_at == now.date()


def test_get_returned_letter_summary_orders_by_reported_at(sample_service):
    now = datetime.utcnow()
    last_month = datetime.utcnow() - timedelta(days=30)
    create_returned_letter(sample_service, reported_at=now)
    create_returned_letter(sample_service, reported_at=now)
    create_returned_letter(sample_service, reported_at=now)
    create_returned_letter(sample_service, reported_at=last_month)
    create_returned_letter(sample_service, reported_at=last_month)
    create_returned_letter()  # returned letter for a different service

    results = get_returned_letter_summary(sample_service.id)

    assert len(results) == 2
    assert results[0].reported_at == now.date()
    assert results[0].returned_letter_count == 3
    assert results[1].reported_at == last_month.date()
    assert results[1].returned_letter_count == 2


def test_fetch_returned_letters(sample_service):
    today = datetime.now()
    last_month = datetime.now() - timedelta(days=30)

    create_returned_letter(service=sample_service, reported_at=today)
    create_returned_letter(service=sample_service, reported_at=today)
    create_returned_letter(service=sample_service, reported_at=last_month)

    results = fetch_returned_letters(service_id=sample_service.id, report_date=today.date())

    assert len(results) == 2
