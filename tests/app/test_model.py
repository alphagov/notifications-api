import pytest

from freezegun import freeze_time
from sqlalchemy.exc import IntegrityError

from app import encryption
from app.models import (
    ServiceWhitelist,
    Notification,
    SMS_TYPE,
    MOBILE_TYPE,
    EMAIL_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENDING,
    NOTIFICATION_PENDING,
    NOTIFICATION_FAILED,
    NOTIFICATION_STATUS_LETTER_ACCEPTED,
    NOTIFICATION_STATUS_LETTER_RECEIVED,
    NOTIFICATION_STATUS_TYPES_FAILED,
    NOTIFICATION_TECHNICAL_FAILURE,
    PRECOMPILED_TEMPLATE_NAME
)

from tests.app.db import (
    create_notification,
    create_service,
    create_inbound_number,
    create_reply_to_email,
    create_letter_contact,
    create_template
)


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
    (NOTIFICATION_STATUS_LETTER_ACCEPTED, [NOTIFICATION_SENDING, NOTIFICATION_CREATED]),
    (NOTIFICATION_CREATED, [NOTIFICATION_CREATED]),
    (NOTIFICATION_TECHNICAL_FAILURE, [NOTIFICATION_TECHNICAL_FAILURE]),
    # passing in lists containing single statuses
    ([NOTIFICATION_FAILED], NOTIFICATION_STATUS_TYPES_FAILED),
    ([NOTIFICATION_CREATED], [NOTIFICATION_CREATED]),
    ([NOTIFICATION_TECHNICAL_FAILURE], [NOTIFICATION_TECHNICAL_FAILURE]),
    (NOTIFICATION_STATUS_LETTER_RECEIVED, NOTIFICATION_DELIVERED),
    # passing in lists containing multiple statuses
    ([NOTIFICATION_FAILED, NOTIFICATION_CREATED], NOTIFICATION_STATUS_TYPES_FAILED + [NOTIFICATION_CREATED]),
    ([NOTIFICATION_CREATED, NOTIFICATION_PENDING], [NOTIFICATION_CREATED, NOTIFICATION_PENDING]),
    ([NOTIFICATION_CREATED, NOTIFICATION_TECHNICAL_FAILURE], [NOTIFICATION_CREATED, NOTIFICATION_TECHNICAL_FAILURE]),
    (
        [NOTIFICATION_FAILED, NOTIFICATION_STATUS_LETTER_ACCEPTED],
        NOTIFICATION_STATUS_TYPES_FAILED + [NOTIFICATION_SENDING, NOTIFICATION_CREATED]
    ),
    # checking we don't end up with duplicates
    (
        [NOTIFICATION_FAILED, NOTIFICATION_CREATED, NOTIFICATION_TECHNICAL_FAILURE],
        NOTIFICATION_STATUS_TYPES_FAILED + [NOTIFICATION_CREATED]
    ),
])
def test_status_conversion(initial_statuses, expected_statuses):
    converted_statuses = Notification.substitute_status(initial_statuses)
    assert len(converted_statuses) == len(expected_statuses)
    assert set(converted_statuses) == set(expected_statuses)


@freeze_time("2016-01-01 11:09:00.000000")
@pytest.mark.parametrize('template_type, recipient', [
    ('sms', '+447700900855'),
    ('email', 'foo@bar.com'),
])
def test_notification_for_csv_returns_correct_type(sample_service, template_type, recipient):
    template = create_template(sample_service, template_type=template_type)
    notification = create_notification(template, to_field=recipient)

    serialized = notification.serialize_for_csv()
    assert serialized['template_type'] == template_type


@freeze_time("2016-01-01 11:09:00.000000")
def test_notification_for_csv_returns_correct_job_row_number(sample_job):
    notification = create_notification(sample_job.template, sample_job, job_row_number=0)

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
    ('letter', 'created', 'Accepted'),
    ('letter', 'sending', 'Accepted'),
    ('letter', 'technical-failure', 'Technical failure'),
    ('letter', 'delivered', 'Received')
])
def test_notification_for_csv_returns_formatted_status(
    sample_service,
    template_type,
    status,
    expected_status
):
    template = create_template(sample_service, template_type=template_type)
    notification = create_notification(template, status=status)

    serialized = notification.serialize_for_csv()
    assert serialized['status'] == expected_status


@freeze_time("2017-03-26 23:01:53.321312")
def test_notification_for_csv_returns_bst_correctly(sample_template):
    notification = create_notification(sample_template)

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
    noti = create_notification(sample_letter_template, personalisation={'name': 'hello'})
    noti.template.subject = '((name))'
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


def test_notification_serializes_created_by_name_with_no_created_by_id(client, sample_notification):
    res = sample_notification.serialize()
    assert res['created_by_name'] is None


def test_notification_serializes_created_by_name_with_created_by_id(client, sample_notification, sample_user):
    sample_notification.created_by_id = sample_user.id
    res = sample_notification.serialize()
    assert res['created_by_name'] == sample_user.name


def test_sms_notification_serializes_without_subject(client, sample_template):
    res = sample_template.serialize()
    assert res['subject'] is None


def test_email_notification_serializes_with_subject(client, sample_email_template):
    res = sample_email_template.serialize()
    assert res['subject'] == 'Email Subject'


def test_letter_notification_serializes_with_subject(client, sample_letter_template):
    res = sample_letter_template.serialize()
    assert res['subject'] == 'Template subject'


def test_notification_references_template_history(client, sample_template):
    noti = create_notification(sample_template)
    sample_template.version = 3
    sample_template.content = 'New template content'

    res = noti.serialize()
    assert res['template']['version'] == 1

    assert res['body'] == noti.template.content
    assert noti.template.content != sample_template.content


def test_notification_requires_a_valid_template_version(client, sample_template):
    sample_template.version = 2
    with pytest.raises(IntegrityError):
        create_notification(sample_template)


def test_inbound_number_serializes_with_service(client, notify_db_session):
    service = create_service()
    inbound_number = create_inbound_number(number='1', service_id=service.id)
    serialized_inbound_number = inbound_number.serialize()
    assert serialized_inbound_number.get('id') == str(inbound_number.id)
    assert serialized_inbound_number.get('service').get('id') == str(inbound_number.service.id)
    assert serialized_inbound_number.get('service').get('name') == inbound_number.service.name


def test_inbound_number_returns_inbound_number(client, notify_db_session):
    service = create_service()
    inbound_number = create_inbound_number(number='1', service_id=service.id)

    assert service.get_inbound_number() == inbound_number.number


def test_inbound_number_returns_none_when_no_inbound_number(client, notify_db_session):
    service = create_service()

    assert not service.get_inbound_number()


def test_service_get_default_reply_to_email_address(sample_service):
    create_reply_to_email(service=sample_service, email_address="default@email.com")

    assert sample_service.get_default_reply_to_email_address() == 'default@email.com'


def test_service_get_default_contact_letter(sample_service):
    create_letter_contact(service=sample_service, contact_block='London,\nNW1A 1AA')

    assert sample_service.get_default_letter_contact() == 'London,\nNW1A 1AA'


def test_service_get_default_sms_sender(notify_db_session):
    service = create_service()
    assert service.get_default_sms_sender() == 'testing'


def test_letter_notification_serializes_correctly(client, sample_letter_notification):
    sample_letter_notification.personalisation = {
        'addressline1': 'test',
        'addressline2': 'London',
        'postcode': 'N1',
    }

    json = sample_letter_notification.serialize()
    assert json['line_1'] == 'test'
    assert json['line_2'] == 'London'
    assert json['postcode'] == 'N1'


def test_letter_notification_postcode_can_be_null_for_precompiled_letters(client, sample_letter_notification):
    sample_letter_notification.personalisation = {
        'address_line_1': 'test',
        'address_line_2': 'London',
    }

    json = sample_letter_notification.serialize()
    assert json['line_1'] == 'test'
    assert json['line_2'] == 'London'
    assert json['postcode'] is None


def test_is_precompiled_letter_false(sample_letter_template):
    assert not sample_letter_template.is_precompiled_letter


def test_is_precompiled_letter_true(sample_letter_template):
    sample_letter_template.hidden = True
    sample_letter_template.name = PRECOMPILED_TEMPLATE_NAME
    assert sample_letter_template.is_precompiled_letter


def test_is_precompiled_letter_hidden_true_not_name(sample_letter_template):
    sample_letter_template.hidden = True
    assert not sample_letter_template.is_precompiled_letter


def test_is_precompiled_letter_name_correct_not_hidden(sample_letter_template):
    sample_letter_template.name = PRECOMPILED_TEMPLATE_NAME
    assert not sample_letter_template.is_precompiled_letter
