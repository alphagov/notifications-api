import pytest

from freezegun import freeze_time

from app import encryption
from app.models import (
    ServiceWhitelist,
    Notification,
    SMS_TYPE,
    MOBILE_TYPE,
    EMAIL_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_PENDING,
    NOTIFICATION_FAILED,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_STATUS_TYPES_FAILED
)
from tests.app.conftest import (
    sample_template as create_sample_template,
    sample_notification_with_job as create_sample_notification_with_job
)
from tests.app.db import create_notification


@pytest.mark.parametrize('mobile_number', [
    '07700 900678',
    '+44 7700 900678'
])
def test_should_build_service_whitelist_from_mobile_number(mobile_number):
    service_whitelist = ServiceWhitelist.from_string('service_id', MOBILE_TYPE, mobile_number)

    assert service_whitelist.recipient == mobile_number


@pytest.mark.parametrize('email_address', [
    'test@example.com'
])
def test_should_build_service_whitelist_from_email_address(email_address):
    service_whitelist = ServiceWhitelist.from_string('service_id', EMAIL_TYPE, email_address)

    assert service_whitelist.recipient == email_address


@pytest.mark.parametrize('contact, recipient_type', [
    ('', None),
    ('07700dsadsad', MOBILE_TYPE),
    ('gmail.com', EMAIL_TYPE)
])
def test_should_not_build_service_whitelist_from_invalid_contact(recipient_type, contact):
    with pytest.raises(ValueError):
        ServiceWhitelist.from_string('service_id', recipient_type, contact)


@pytest.mark.parametrize('initial_statuses, expected_statuses', [
    # passing in single statuses as strings
    (NOTIFICATION_FAILED, NOTIFICATION_STATUS_TYPES_FAILED),
    (NOTIFICATION_CREATED, NOTIFICATION_CREATED),
    (NOTIFICATION_TECHNICAL_FAILURE, NOTIFICATION_TECHNICAL_FAILURE),
    # passing in lists containing single statuses
    ([NOTIFICATION_FAILED], NOTIFICATION_STATUS_TYPES_FAILED),
    ([NOTIFICATION_CREATED], [NOTIFICATION_CREATED]),
    ([NOTIFICATION_TECHNICAL_FAILURE], [NOTIFICATION_TECHNICAL_FAILURE]),
    # passing in lists containing multiple statuses
    ([NOTIFICATION_FAILED, NOTIFICATION_CREATED], NOTIFICATION_STATUS_TYPES_FAILED + [NOTIFICATION_CREATED]),
    ([NOTIFICATION_CREATED, NOTIFICATION_PENDING], [NOTIFICATION_CREATED, NOTIFICATION_PENDING]),
    ([NOTIFICATION_CREATED, NOTIFICATION_TECHNICAL_FAILURE], [NOTIFICATION_CREATED, NOTIFICATION_TECHNICAL_FAILURE]),
    # checking we don't end up with duplicates
    (
        [NOTIFICATION_FAILED, NOTIFICATION_CREATED, NOTIFICATION_TECHNICAL_FAILURE],
        NOTIFICATION_STATUS_TYPES_FAILED + [NOTIFICATION_CREATED]
    ),
])
def test_status_conversion_handles_failed_statuses(initial_statuses, expected_statuses):
    converted_statuses = Notification.substitute_status(initial_statuses)
    assert len(converted_statuses) == len(expected_statuses)
    assert set(converted_statuses) == set(expected_statuses)


@freeze_time("2016-01-01 11:09:00.000000")
@pytest.mark.parametrize('template_type, recipient', [
    ('sms', '+447700900855'),
    ('email', 'foo@bar.com'),
])
def test_notification_for_csv_returns_correct_type(notify_db, notify_db_session, template_type, recipient):
    template = create_sample_template(notify_db, notify_db_session, template_type=template_type)
    notification = create_sample_notification_with_job(
        notify_db,
        notify_db_session,
        template=template,
        to_field=recipient
    )

    serialized = notification.serialize_for_csv()
    assert serialized['template_type'] == template_type


@freeze_time("2016-01-01 11:09:00.000000")
def test_notification_for_csv_returns_correct_job_row_number(notify_db, notify_db_session):
    notification = create_sample_notification_with_job(
        notify_db,
        notify_db_session,
        job_row_number=0
    )

    serialized = notification.serialize_for_csv()
    assert serialized['row_number'] == 1


@freeze_time("2016-01-30 12:39:58.321312")
@pytest.mark.parametrize('template_type, status, expected_status', [
    ('email', 'failed', 'Failed'),
    ('email', 'technical-failure', 'Technical failure'),
    ('email', 'temporary-failure', 'Inbox not accepting messages right now'),
    ('email', 'permanent-failure', 'Email address doesn’t exist'),
    ('sms', 'temporary-failure', 'Phone not accepting messages right now'),
    ('sms', 'permanent-failure', 'Phone number doesn’t exist'),
    ('sms', 'sent', 'Sent internationally'),
    ('letter', 'permanent-failure', 'Permanent failure'),
    ('letter', 'delivered', 'Delivered')
])
def test_notification_for_csv_returns_formatted_status(
    notify_db,
    notify_db_session,
    template_type,
    status,
    expected_status
):
    template = create_sample_template(notify_db, notify_db_session, template_type=template_type)
    notification = create_sample_notification_with_job(
        notify_db,
        notify_db_session,
        status=status,
        template=template
    )

    serialized = notification.serialize_for_csv()
    assert serialized['status'] == expected_status


@freeze_time("2017-03-26 23:01:53.321312")
def test_notification_for_csv_returns_bst_correctly(notify_db, notify_db_session):
    notification = create_sample_notification_with_job(
        notify_db,
        notify_db_session,
        job_row_number=100,
        status='permanent-failure'
    )

    serialized = notification.serialize_for_csv()
    assert serialized['created_at'] == 'Monday 27 March 2017 at 00:01'


def test_notification_personalisation_getter_returns_empty_dict_from_None():
    noti = Notification()
    noti._personalisation = None
    assert noti.personalisation == {}


def test_notification_personalisation_getter_always_returns_empty_dict():
    noti = Notification()
    noti._personalisation = encryption.encrypt({})
    assert noti.personalisation == {}


@pytest.mark.parametrize('input_value', [
    None,
    {}
])
def test_notification_personalisation_setter_always_sets_empty_dict(input_value):
    noti = Notification()
    noti.personalisation = input_value

    assert noti._personalisation == encryption.encrypt({})


def test_notification_subject_is_none_for_sms():
    assert Notification(notification_type=SMS_TYPE).subject is None


def test_notification_subject_fills_in_placeholders_for_email(sample_email_template_with_placeholders):
    noti = create_notification(sample_email_template_with_placeholders, personalisation={'name': 'hello'})
    assert noti.subject == 'hello'


def test_notification_subject_fills_in_placeholders_for_letter(sample_letter_template):
    sample_letter_template.subject = '((name))'
    noti = create_notification(sample_letter_template, personalisation={'name': 'hello'})
    assert noti.subject == 'hello'


def test_letter_notification_serializes_with_address(client, sample_letter_notification):
    sample_letter_notification.personalisation = {
        'address_line_1': 'foo',
        'address_line_3': 'bar',
        'address_line_5': None,
        'postcode': 'SW1 1AA'
    }
    res = sample_letter_notification.serialize()
    assert res['line_1'] == 'foo'
    assert res['line_2'] is None
    assert res['line_3'] == 'bar'
    assert res['line_4'] is None
    assert res['line_5'] is None
    assert res['line_6'] is None
    assert res['postcode'] == 'SW1 1AA'


def test_sms_notification_serializes_without_subject(client, sample_template):
    res = sample_template.serialize()
    assert res['subject'] is None


def test_email_notification_serializes_with_subject(client, sample_email_template):
    res = sample_email_template.serialize()
    assert res['subject'] == 'Email Subject'


def test_letter_notification_serializes_with_subject(client, sample_letter_template):
    res = sample_letter_template.serialize()
    assert res['subject'] == 'Template subject'
