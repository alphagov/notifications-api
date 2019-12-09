from datetime import datetime

from freezegun import freeze_time

from app.dao.returned_letters_dao import insert_or_update_returned_letters
from app.models import ReturnedLetter
from tests.app.db import create_notification, create_notification_history


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
            assert x.reported_at == datetime(2019, 12, 9, 13, 30)
            assert x.notification_id in [notification.id, history.id]

    with freeze_time('2019-12-10 14:20'):
        insert_or_update_returned_letters(['ref1', 'ref2'])

        returned_letters = ReturnedLetter.query.all()
        assert len(returned_letters) == 2
        for x in returned_letters:
            assert x.reported_at == datetime(2019, 12, 10, 14, 20)
            assert x.notification_id in [notification.id, history.id]


def test_insert_or_update_returned_letters_when_no_notification(sample_letter_template):
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
