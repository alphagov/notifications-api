from collections import namedtuple, defaultdict
from datetime import datetime, date

import pytest
from freezegun import freeze_time
from flask import current_app

from app.exceptions import DVLAException, NotificationTechnicalFailureException
from app.models import (
    Notification,
    NotificationHistory,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENDING,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_TECHNICAL_FAILURE,
)
from app.celery.tasks import (
    check_billable_units,
    get_billing_date_in_bst_from_filename,
    persist_daily_sorted_letter_counts,
    process_updates_from_file,
    update_letter_notifications_statuses,
    update_letter_notifications_to_error,
    update_letter_notifications_to_sent_to_dvla
)
from app.dao.daily_sorted_letter_dao import dao_get_daily_sorted_letter_by_billing_day

from tests.app.db import create_notification, create_service_callback_api
from tests.conftest import set_config


@pytest.fixture
def notification_update():
    """
    Returns a namedtuple to use as the argument for the check_billable_units function
    """
    NotificationUpdate = namedtuple('NotificationUpdate', ['reference', 'status', 'page_count', 'cost_threshold'])
    return NotificationUpdate('REFERENCE_ABC', 'sent', '1', 'cost')


def test_update_letter_notifications_statuses_raises_for_invalid_format(notify_api, mocker):
    invalid_file = 'ref-foo|Sent|1|Unsorted\nref-bar|Sent|2'
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=invalid_file)

    with pytest.raises(DVLAException) as e:
        update_letter_notifications_statuses(filename='NOTIFY-20170823160812-RSP.TXT')
    assert 'DVLA response file: {} has an invalid format'.format('NOTIFY-20170823160812-RSP.TXT') in str(e)


def test_update_letter_notification_statuses_when_notification_does_not_exist_updates_notification_history(
    sample_letter_template,
    mocker
):
    valid_file = 'ref-foo|Sent|1|Unsorted'
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)
    notification = create_notification(sample_letter_template, reference='ref-foo', status=NOTIFICATION_SENDING,
                                       billable_units=1)
    Notification.query.filter_by(id=notification.id).delete()

    update_letter_notifications_statuses(filename="NOTIFY-20170823160812-RSP.TXT")

    updated_history = NotificationHistory.query.filter_by(id=notification.id).one()
    assert updated_history.status == NOTIFICATION_DELIVERED


def test_update_letter_notifications_statuses_raises_dvla_exception(notify_api, mocker, sample_letter_template):
    valid_file = 'ref-foo|Failed|1|Unsorted'
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)
    create_notification(sample_letter_template, reference='ref-foo', status=NOTIFICATION_SENDING,
                        billable_units=0)

    with pytest.raises(DVLAException) as e:
        update_letter_notifications_statuses(filename="failed.txt")
    failed = ["ref-foo"]
    assert "DVLA response file: {filename} has failed letters with notification.reference {failures}".format(
        filename="failed.txt", failures=failed
    ) in str(e)


def test_update_letter_notifications_statuses_raises_error_for_unknown_sorted_status(
    notify_api,
    mocker,
    sample_letter_template
):
    sent_letter_1 = create_notification(sample_letter_template, reference='ref-foo', status=NOTIFICATION_SENDING)
    sent_letter_2 = create_notification(sample_letter_template, reference='ref-bar', status=NOTIFICATION_SENDING)
    valid_file = '{}|Sent|1|Unsorted\n{}|Sent|2|Error'.format(
        sent_letter_1.reference, sent_letter_2.reference)

    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)

    with pytest.raises(DVLAException) as e:
        update_letter_notifications_statuses(filename='NOTIFY-20170823160812-RSP.TXT')

    assert "DVLA response file: {filename} contains unknown Sorted status {unknown_status}".format(
        filename="NOTIFY-20170823160812-RSP.TXT", unknown_status="{'Error'}"
    ) in str(e)


def test_update_letter_notifications_statuses_still_raises_temp_failure_error_with_unknown_sorted_status(
    notify_api,
    mocker,
    sample_letter_template
):
    valid_file = 'ref-foo|Failed|1|unknown'
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)
    create_notification(sample_letter_template, reference='ref-foo', status=NOTIFICATION_SENDING,
                        billable_units=0)

    with pytest.raises(DVLAException) as e:
        update_letter_notifications_statuses(filename="failed.txt")

    failed = ["ref-foo"]
    assert "DVLA response file: {filename} has failed letters with notification.reference {failures}".format(
        filename="failed.txt", failures=failed
    ) in str(e)


def test_update_letter_notifications_statuses_calls_with_correct_bucket_location(notify_api, mocker):
    s3_mock = mocker.patch('app.celery.tasks.s3.get_s3_object')

    with set_config(notify_api, 'NOTIFY_EMAIL_DOMAIN', 'foo.bar'):
        update_letter_notifications_statuses(filename='NOTIFY-20170823160812-RSP.TXT')
        s3_mock.assert_called_with('{}-ftp'.format(
            current_app.config['NOTIFY_EMAIL_DOMAIN']),
            'NOTIFY-20170823160812-RSP.TXT'
        )


def test_update_letter_notifications_statuses_builds_updates_from_content(notify_api, mocker):
    valid_file = 'ref-foo|Sent|1|Unsorted\nref-bar|Sent|2|Sorted'
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)
    update_mock = mocker.patch('app.celery.tasks.process_updates_from_file')

    update_letter_notifications_statuses(filename='NOTIFY-20170823160812-RSP.TXT')

    update_mock.assert_called_with('ref-foo|Sent|1|Unsorted\nref-bar|Sent|2|Sorted')


def test_update_letter_notifications_statuses_builds_updates_list(notify_api, mocker):
    valid_file = 'ref-foo|Sent|1|Unsorted\nref-bar|Sent|2|Sorted'
    updates = process_updates_from_file(valid_file)

    assert len(updates) == 2

    assert updates[0].reference == 'ref-foo'
    assert updates[0].status == 'Sent'
    assert updates[0].page_count == '1'
    assert updates[0].cost_threshold == 'Unsorted'

    assert updates[1].reference == 'ref-bar'
    assert updates[1].status == 'Sent'
    assert updates[1].page_count == '2'
    assert updates[1].cost_threshold == 'Sorted'


def test_update_letter_notifications_statuses_persisted(notify_api, mocker, sample_letter_template):
    sent_letter = create_notification(sample_letter_template, reference='ref-foo', status=NOTIFICATION_SENDING,
                                      billable_units=1)
    failed_letter = create_notification(sample_letter_template, reference='ref-bar', status=NOTIFICATION_SENDING,
                                        billable_units=2)
    create_service_callback_api(service=sample_letter_template.service, url="https://original_url.com")
    valid_file = '{}|Sent|1|Unsorted\n{}|Failed|2|Sorted'.format(
        sent_letter.reference, failed_letter.reference)
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)

    with pytest.raises(expected_exception=DVLAException) as e:
        update_letter_notifications_statuses(filename='NOTIFY-20170823160812-RSP.TXT')

    assert sent_letter.status == NOTIFICATION_DELIVERED
    assert sent_letter.billable_units == 1
    assert sent_letter.updated_at
    assert failed_letter.status == NOTIFICATION_TEMPORARY_FAILURE
    assert failed_letter.billable_units == 2
    assert failed_letter.updated_at
    assert "DVLA response file: {filename} has failed letters with notification.reference {failures}".format(
        filename="NOTIFY-20170823160812-RSP.TXT", failures=[format(failed_letter.reference)]) in str(e)


def test_update_letter_notifications_statuses_persists_daily_sorted_letter_count(
    notify_api,
    mocker,
    sample_letter_template
):
    sent_letter_1 = create_notification(sample_letter_template, reference='ref-foo', status=NOTIFICATION_SENDING)
    sent_letter_2 = create_notification(sample_letter_template, reference='ref-bar', status=NOTIFICATION_SENDING)
    valid_file = '{}|Sent|1|Unsorted\n{}|Sent|2|Sorted'.format(
        sent_letter_1.reference, sent_letter_2.reference)

    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)
    persist_letter_count_mock = mocker.patch('app.celery.tasks.persist_daily_sorted_letter_counts')

    update_letter_notifications_statuses(filename='NOTIFY-20170823160812-RSP.TXT')

    persist_letter_count_mock.assert_called_once_with(day=date(2017, 8, 23),
                                                      file_name='NOTIFY-20170823160812-RSP.TXT',
                                                      sorted_letter_counts={'Unsorted': 1, 'Sorted': 1})


def test_update_letter_notifications_statuses_persists_daily_sorted_letter_count_with_no_sorted_values(
    notify_api,
    mocker,
    sample_letter_template,
    notify_db_session
):
    sent_letter_1 = create_notification(sample_letter_template, reference='ref-foo', status=NOTIFICATION_SENDING)
    sent_letter_2 = create_notification(sample_letter_template, reference='ref-bar', status=NOTIFICATION_SENDING)
    valid_file = '{}|Sent|1|Unsorted\n{}|Sent|2|Unsorted'.format(
        sent_letter_1.reference, sent_letter_2.reference)
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)

    update_letter_notifications_statuses(filename='NOTIFY-20170823160812-RSP.TXT')

    daily_sorted_letter = dao_get_daily_sorted_letter_by_billing_day(date(2017, 8, 23))

    assert daily_sorted_letter.unsorted_count == 2
    assert daily_sorted_letter.sorted_count == 0


def test_update_letter_notifications_does_not_call_send_callback_if_no_db_entry(notify_api, mocker,
                                                                                sample_letter_template):
    sent_letter = create_notification(sample_letter_template, reference='ref-foo', status=NOTIFICATION_SENDING,
                                      billable_units=0)
    valid_file = '{}|Sent|1|Unsorted\n'.format(sent_letter.reference)
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)

    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )

    update_letter_notifications_statuses(filename='NOTIFY-20170823160812-RSP.TXT')
    send_mock.assert_not_called()


def test_update_letter_notifications_to_sent_to_dvla_updates_based_on_notification_references(
    client,
    sample_letter_template
):
    first = create_notification(sample_letter_template, reference='first ref')
    second = create_notification(sample_letter_template, reference='second ref')

    dt = datetime.utcnow()
    with freeze_time(dt):
        update_letter_notifications_to_sent_to_dvla([first.reference])

    assert first.status == NOTIFICATION_SENDING
    assert first.sent_by == 'dvla'
    assert first.sent_at == dt
    assert first.updated_at == dt
    assert second.status == NOTIFICATION_CREATED


def test_update_letter_notifications_to_error_updates_based_on_notification_references(
    client,
    sample_letter_template,
    mocker
):
    first = create_notification(sample_letter_template, reference='first ref')
    second = create_notification(sample_letter_template, reference='second ref')
    create_service_callback_api(service=sample_letter_template.service, url="https://original_url.com")
    dt = datetime.utcnow()
    with freeze_time(dt):
        with pytest.raises(NotificationTechnicalFailureException) as e:
            update_letter_notifications_to_error([first.reference])
    assert first.reference in e.value.message

    assert first.status == NOTIFICATION_TECHNICAL_FAILURE
    assert first.sent_by is None
    assert first.sent_at is None
    assert first.updated_at == dt
    assert second.status == NOTIFICATION_CREATED


def test_check_billable_units_when_billable_units_matches_page_count(
    client,
    sample_letter_template,
    mocker,
    notification_update
):
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.error')

    create_notification(sample_letter_template, reference='REFERENCE_ABC', billable_units=1)

    check_billable_units(notification_update)

    mock_logger.assert_not_called()


def test_check_billable_units_when_billable_units_does_not_match_page_count(
    client,
    sample_letter_template,
    mocker,
    notification_update
):
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.exception')

    notification = create_notification(sample_letter_template, reference='REFERENCE_ABC', billable_units=3)

    check_billable_units(notification_update)

    mock_logger.assert_called_once_with(
        'Notification with id {} has 3 billable_units but DVLA says page count is 1'.format(notification.id)
    )


@pytest.mark.parametrize('filename_date, billing_date', [
    ('20170820230000', date(2017, 8, 21)),
    ('20170120230000', date(2017, 1, 20))
])
def test_get_billing_date_in_bst_from_filename(filename_date, billing_date):
    filename = 'NOTIFY-{}-RSP.TXT'.format(filename_date)
    result = get_billing_date_in_bst_from_filename(filename)

    assert result == billing_date


@freeze_time("2018-01-11 09:00:00")
def test_persist_daily_sorted_letter_counts_saves_sorted_and_unsorted_values(client, notify_db_session):
    letter_counts = defaultdict(int, **{'Unsorted': 5, 'Sorted': 1})
    persist_daily_sorted_letter_counts(date.today(), "test.txt", letter_counts)
    day = dao_get_daily_sorted_letter_by_billing_day(date.today())

    assert day.unsorted_count == 5
    assert day.sorted_count == 1
