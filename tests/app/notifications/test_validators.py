import pytest
from freezegun import freeze_time
from flask import current_app
from notifications_utils import SMS_CHAR_COUNT_LIMIT

import app
from app.dao import templates_dao
from app.models import SMS_TYPE, EMAIL_TYPE, LETTER_TYPE
from app.notifications.process_notifications import create_content_for_notification
from app.notifications.validators import (
    check_content_char_count,
    check_if_service_can_send_files_by_email,
    check_notification_content_is_not_empty,
    check_service_over_daily_message_limit,
    check_template_is_for_notification_type,
    check_template_is_active,
    check_service_over_api_rate_limit,
    check_service_email_reply_to_id,
    check_service_sms_sender_id,
    check_service_letter_contact_id,
    check_reply_to,
    service_can_send_to_recipient,
    validate_and_format_recipient,
    validate_template,
)
from app.json_models import TemplateJSONModel
from app.utils import get_template_instance

from app.v2.errors import (
    BadRequestError,
    TooManyRequestsError,
    RateLimitError)

from tests.conftest import set_config
from tests.app.db import (
    create_api_key,
    create_letter_contact,
    create_notification,
    create_reply_to_email,
    create_service,
    create_service_sms_sender,
    create_service_whitelist,
    create_template,
)


# all of these tests should have redis enabled (except where we specifically disable it)
@pytest.fixture(scope='module', autouse=True)
def enable_redis(notify_api):
    with set_config(notify_api, 'REDIS_ENABLED', True):
        yield


@pytest.mark.parametrize('key_type', ['test', 'team', 'normal'])
def test_check_service_message_limit_in_cache_with_unrestricted_service_is_allowed(
        key_type,
        sample_service,
        mocker):
    mocker.patch('app.notifications.validators.redis_store.get', return_value=1)
    mocker.patch('app.notifications.validators.redis_store.set')
    mocker.patch('app.notifications.validators.services_dao')

    check_service_over_daily_message_limit(key_type, sample_service)
    app.notifications.validators.redis_store.set.assert_not_called()
    assert not app.notifications.validators.services_dao.mock_calls


@pytest.mark.parametrize('key_type', ['test', 'team', 'normal'])
def test_check_service_message_limit_in_cache_under_message_limit_passes(
        key_type,
        sample_service,
        mocker):
    mocker.patch('app.notifications.validators.redis_store.get', return_value=1)
    mocker.patch('app.notifications.validators.redis_store.set')
    mocker.patch('app.notifications.validators.services_dao')
    check_service_over_daily_message_limit(key_type, sample_service)
    app.notifications.validators.redis_store.set.assert_not_called()
    assert not app.notifications.validators.services_dao.mock_calls


def test_should_not_interact_with_cache_for_test_key(sample_service, mocker):
    mocker.patch('app.notifications.validators.redis_store')
    check_service_over_daily_message_limit('test', sample_service)
    assert not app.notifications.validators.redis_store.mock_calls


@pytest.mark.parametrize('key_type', ['team', 'normal'])
def test_should_set_cache_value_as_value_from_database_if_cache_not_set(
        key_type,
        sample_template,
        sample_service,
        mocker
):
    with freeze_time("2016-01-01 12:00:00.000000"):
        for x in range(5):
            create_notification(sample_template)
        mocker.patch('app.notifications.validators.redis_store.get', return_value=None)
        mocker.patch('app.notifications.validators.redis_store.set')
        check_service_over_daily_message_limit(key_type, sample_service)
        app.notifications.validators.redis_store.set.assert_called_with(
            str(sample_service.id) + "-2016-01-01-count", 5, ex=3600
        )


def test_should_not_access_database_if_redis_disabled(notify_api, sample_service, mocker):
    with set_config(notify_api, 'REDIS_ENABLED', False):
        db_mock = mocker.patch('app.notifications.validators.services_dao')

        check_service_over_daily_message_limit('normal', sample_service)

        assert db_mock.method_calls == []


@pytest.mark.parametrize('key_type', ['team', 'normal'])
def test_check_service_message_limit_over_message_limit_fails(key_type, sample_service, mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):
        mocker.patch('app.redis_store.get', return_value=None)
        mocker.patch('app.notifications.validators.redis_store.set')

        sample_service.restricted = True
        sample_service.message_limit = 4
        template = create_template(sample_service)

        for x in range(5):
            create_notification(template)
        with pytest.raises(TooManyRequestsError) as e:
            check_service_over_daily_message_limit(key_type, sample_service)
        assert e.value.status_code == 429
        assert e.value.message == 'Exceeded send limits (4) for today'
        assert e.value.fields == []
        app.notifications.validators.redis_store.set.assert_called_with(
            str(sample_service.id) + "-2016-01-01-count", 5, ex=3600
        )


@pytest.mark.parametrize('key_type', ['team', 'normal'])
def test_check_service_message_limit_in_cache_over_message_limit_fails(
        notify_db_session,
        key_type,
        mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):
        mocker.patch('app.redis_store.get', return_value=5)
        mocker.patch('app.notifications.validators.redis_store.set')
        mocker.patch('app.notifications.validators.services_dao')

        service = create_service(restricted=True, message_limit=4)
        with pytest.raises(TooManyRequestsError) as e:
            check_service_over_daily_message_limit(key_type, service)
        assert e.value.status_code == 429
        assert e.value.message == 'Exceeded send limits (4) for today'
        assert e.value.fields == []
        app.notifications.validators.redis_store.set.assert_not_called()
        assert not app.notifications.validators.services_dao.mock_calls


@pytest.mark.parametrize('template_type, notification_type',
                         [(EMAIL_TYPE, EMAIL_TYPE),
                          (SMS_TYPE, SMS_TYPE)])
def test_check_template_is_for_notification_type_pass(template_type, notification_type):
    assert check_template_is_for_notification_type(notification_type=notification_type,
                                                   template_type=template_type) is None


@pytest.mark.parametrize('template_type, notification_type',
                         [(SMS_TYPE, EMAIL_TYPE),
                          (EMAIL_TYPE, SMS_TYPE)])
def test_check_template_is_for_notification_type_fails_when_template_type_does_not_match_notification_type(
        template_type, notification_type):
    with pytest.raises(BadRequestError) as e:
        check_template_is_for_notification_type(notification_type=notification_type,
                                                template_type=template_type)
    assert e.value.status_code == 400
    error_message = '{0} template is not suitable for {1} notification'.format(template_type, notification_type)
    assert e.value.message == error_message
    assert e.value.fields == [{'template': error_message}]


def test_check_template_is_active_passes(sample_template):
    assert check_template_is_active(sample_template) is None


def test_check_template_is_active_fails(sample_template):
    sample_template.archived = True
    from app.dao.templates_dao import dao_update_template
    dao_update_template(sample_template)
    with pytest.raises(BadRequestError) as e:
        check_template_is_active(sample_template)
    assert e.value.status_code == 400
    assert e.value.message == 'Template has been deleted'
    assert e.value.fields == [{'template': 'Template has been deleted'}]


@pytest.mark.parametrize('key_type',
                         ['test', 'normal'])
def test_service_can_send_to_recipient_passes(key_type, notify_db_session):
    trial_mode_service = create_service(service_name='trial mode', restricted=True)
    assert service_can_send_to_recipient(trial_mode_service.users[0].email_address,
                                         key_type,
                                         trial_mode_service) is None
    assert service_can_send_to_recipient(trial_mode_service.users[0].mobile_number,
                                         key_type,
                                         trial_mode_service) is None


@pytest.mark.parametrize('key_type',
                         ['test', 'normal'])
def test_service_can_send_to_recipient_passes_for_live_service_non_team_member(key_type, sample_service):
    assert service_can_send_to_recipient("some_other_email@test.com",
                                         key_type,
                                         sample_service) is None
    assert service_can_send_to_recipient('07513332413',
                                         key_type,
                                         sample_service) is None


def test_service_can_send_to_recipient_passes_for_whitelisted_recipient_passes(sample_service):
    create_service_whitelist(sample_service, email_address="some_other_email@test.com")
    assert service_can_send_to_recipient("some_other_email@test.com",
                                         'team',
                                         sample_service) is None
    create_service_whitelist(sample_service, mobile_number='07513332413')
    assert service_can_send_to_recipient('07513332413',
                                         'team',
                                         sample_service) is None


@pytest.mark.parametrize('recipient', [
    {"email_address": "some_other_email@test.com"},
    {"mobile_number": "07513332413"},
])
def test_service_can_send_to_recipient_fails_when_ignoring_whitelist(
    notify_db,
    notify_db_session,
    sample_service,
    recipient,
):
    create_service_whitelist(sample_service, **recipient)
    with pytest.raises(BadRequestError) as exec_info:
        service_can_send_to_recipient(
            next(iter(recipient.values())),
            'team',
            sample_service,
            allow_whitelisted_recipients=False,
        )
    assert exec_info.value.status_code == 400
    assert exec_info.value.message == 'Can’t send to this recipient using a team-only API key'
    assert exec_info.value.fields == []


@pytest.mark.parametrize('recipient', ['07513332413', 'some_other_email@test.com'])
@pytest.mark.parametrize('key_type, error_message',
                         [('team', 'Can’t send to this recipient using a team-only API key'),
                          ('normal',
                           "Can’t send to this recipient when service is in trial mode – see https://www.notifications.service.gov.uk/trial-mode")])  # noqa
def test_service_can_send_to_recipient_fails_when_recipient_is_not_on_team(
    recipient,
    key_type,
    error_message,
    notify_db_session,
):
    trial_mode_service = create_service(service_name='trial mode', restricted=True)
    with pytest.raises(BadRequestError) as exec_info:
        service_can_send_to_recipient(recipient,
                                      key_type,
                                      trial_mode_service)
    assert exec_info.value.status_code == 400
    assert exec_info.value.message == error_message
    assert exec_info.value.fields == []


def test_service_can_send_to_recipient_fails_when_mobile_number_is_not_on_team(sample_service):
    with pytest.raises(BadRequestError) as e:
        service_can_send_to_recipient("0758964221",
                                      'team',
                                      sample_service)
    assert e.value.status_code == 400
    assert e.value.message == 'Can’t send to this recipient using a team-only API key'
    assert e.value.fields == []


@pytest.mark.parametrize('char_count', [612, 0, 494, 200, 918])
@pytest.mark.parametrize('show_prefix', [True, False])
@pytest.mark.parametrize('template_type', ['sms', 'email', 'letter'])
def test_check_content_char_count_passes(notify_db_session, show_prefix, char_count, template_type):
    service = create_service(prefix_sms=show_prefix)
    t = create_template(service=service, content='a' * char_count, template_type=template_type)
    template = templates_dao.dao_get_template_by_id_and_service_id(template_id=t.id, service_id=service.id)
    template_with_content = get_template_instance(template=template.__dict__, values={})
    assert check_content_char_count(template_with_content) is None


@pytest.mark.parametrize('char_count', [919, 6000])
@pytest.mark.parametrize('show_prefix', [True, False])
def test_check_content_char_count_fails(notify_db_session, show_prefix, char_count):
    with pytest.raises(BadRequestError) as e:
        service = create_service(prefix_sms=show_prefix)
        t = create_template(service=service, content='a' * char_count, template_type='sms')
        template = templates_dao.dao_get_template_by_id_and_service_id(template_id=t.id, service_id=service.id)
        template_with_content = get_template_instance(template=template.__dict__, values={})
        check_content_char_count(template_with_content)
    assert e.value.status_code == 400
    assert e.value.message == f'Text messages cannot be longer than {SMS_CHAR_COUNT_LIMIT} characters. ' \
                              f'Your message is {char_count} characters'
    assert e.value.fields == []


@pytest.mark.parametrize('template_type', ['email', 'letter'])
def test_check_content_char_count_passes_for_long_email_or_letter(sample_service, template_type):
    t = create_template(service=sample_service, content='a' * 1000, template_type=template_type)
    template = templates_dao.dao_get_template_by_id_and_service_id(template_id=t.id,
                                                                   service_id=t.service_id)
    template_with_content = get_template_instance(template=template.__dict__, values={})
    assert check_content_char_count(template_with_content) is None


def test_check_notification_content_is_not_empty_passes(notify_api, mocker, sample_service):
    template_id = create_template(sample_service, content="Content is not empty").id
    template = TemplateJSONModel.from_id_and_service_id(
        template_id=template_id,
        service_id=sample_service.id
    )
    template_with_content = create_content_for_notification(template, {})
    assert check_notification_content_is_not_empty(template_with_content) is None


@pytest.mark.parametrize('template_content,notification_values', [
    ("", {}),
    ("((placeholder))", {"placeholder": ""})
])
def test_check_notification_content_is_not_empty_fails(
    notify_api, mocker, sample_service, template_content, notification_values
):
    template_id = create_template(sample_service, content=template_content).id
    template = TemplateJSONModel.from_id_and_service_id(
        template_id=template_id,
        service_id=sample_service.id
    )
    template_with_content = create_content_for_notification(template, notification_values)
    with pytest.raises(BadRequestError) as e:
        check_notification_content_is_not_empty(template_with_content)
    assert e.value.status_code == 400
    assert e.value.message == 'Your message is empty.'
    assert e.value.fields == []


def test_validate_template(sample_service):
    template = create_template(sample_service, template_type="email")
    validate_template(template.id, {}, sample_service, "email")


def test_validate_template_calls_all_validators(mocker, fake_uuid, sample_service):
    template = create_template(sample_service, template_type="email")
    mock_check_type = mocker.patch('app.notifications.validators.check_template_is_for_notification_type')
    mock_check_if_active = mocker.patch('app.notifications.validators.check_template_is_active')
    mock_create_conent = mocker.patch(
        'app.notifications.validators.create_content_for_notification', return_value="content"
    )
    mock_check_not_empty = mocker.patch('app.notifications.validators.check_notification_content_is_not_empty')
    mock_check_message_is_too_long = mocker.patch('app.notifications.validators.check_content_char_count')
    template, template_with_content = validate_template(template.id, {}, sample_service, "email")

    mock_check_type.assert_called_once_with("email", "email")
    mock_check_if_active.assert_called_once_with(template)
    mock_create_conent.assert_called_once_with(template, {})
    mock_check_not_empty.assert_called_once_with("content")
    mock_check_message_is_too_long.assert_called_once_with("content")


@pytest.mark.parametrize('key_type', ['team', 'live', 'test'])
def test_that_when_exceed_rate_limit_request_fails(
        key_type,
        sample_service,
        mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):

        if key_type == 'live':
            api_key_type = 'normal'
        else:
            api_key_type = key_type

        mocker.patch('app.redis_store.exceeded_rate_limit', return_value=True)
        mocker.patch('app.notifications.validators.services_dao')

        sample_service.restricted = True
        api_key = create_api_key(sample_service, key_type=api_key_type)

        with pytest.raises(RateLimitError) as e:
            check_service_over_api_rate_limit(sample_service, api_key)

        assert app.redis_store.exceeded_rate_limit.called_with(
            "{}-{}".format(str(sample_service.id), api_key.key_type),
            sample_service.rate_limit,
            60
        )
        assert e.value.status_code == 429
        assert e.value.message == 'Exceeded rate limit for key type {} of {} requests per {} seconds'.format(
            key_type.upper(), sample_service.rate_limit, 60
        )
        assert e.value.fields == []


def test_that_when_not_exceeded_rate_limit_request_succeeds(
        sample_service,
        mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):
        mocker.patch('app.redis_store.exceeded_rate_limit', return_value=False)
        mocker.patch('app.notifications.validators.services_dao')

        sample_service.restricted = True
        api_key = create_api_key(sample_service)

        check_service_over_api_rate_limit(sample_service, api_key)
        assert app.redis_store.exceeded_rate_limit.called_with(
            "{}-{}".format(str(sample_service.id), api_key.key_type),
            3000,
            60
        )


def test_should_not_rate_limit_if_limiting_is_disabled(
        sample_service,
        mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):
        current_app.config['API_RATE_LIMIT_ENABLED'] = False

        mocker.patch('app.redis_store.exceeded_rate_limit', return_value=False)
        mocker.patch('app.notifications.validators.services_dao')

        sample_service.restricted = True
        api_key = create_api_key(sample_service)

        check_service_over_api_rate_limit(sample_service, api_key)
        assert not app.redis_store.exceeded_rate_limit.called


@pytest.mark.parametrize('key_type', ['test', 'normal'])
def test_rejects_api_calls_with_international_numbers_if_service_does_not_allow_int_sms(
        key_type,
        notify_db_session,
):
    service = create_service(service_permissions=[SMS_TYPE])
    with pytest.raises(BadRequestError) as e:
        validate_and_format_recipient('20-12-1234-1234', key_type, service, SMS_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == 'Cannot send to international mobile numbers'
    assert e.value.fields == []


@pytest.mark.parametrize('key_type', ['test', 'normal'])
def test_allows_api_calls_with_international_numbers_if_service_does_allow_int_sms(
        key_type, sample_service_full_permissions):
    result = validate_and_format_recipient('20-12-1234-1234', key_type, sample_service_full_permissions, SMS_TYPE)
    assert result == '201212341234'


def test_rejects_api_calls_with_no_recipient():
    with pytest.raises(BadRequestError) as e:
        validate_and_format_recipient(None, 'key_type', 'service', 'SMS_TYPE')
    assert e.value.status_code == 400
    assert e.value.message == "Recipient can't be empty"


@pytest.mark.parametrize('notification_type', ['sms', 'email', 'letter'])
def test_check_service_email_reply_to_id_where_reply_to_id_is_none(notification_type):
    assert check_service_email_reply_to_id(None, None, notification_type) is None


def test_check_service_email_reply_to_where_email_reply_to_is_found(sample_service):
    reply_to_address = create_reply_to_email(sample_service, "test@test.com")
    assert check_service_email_reply_to_id(sample_service.id, reply_to_address.id, EMAIL_TYPE) == "test@test.com"


def test_check_service_email_reply_to_id_where_service_id_is_not_found(sample_service, fake_uuid):
    reply_to_address = create_reply_to_email(sample_service, "test@test.com")
    with pytest.raises(BadRequestError) as e:
        check_service_email_reply_to_id(fake_uuid, reply_to_address.id, EMAIL_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == 'email_reply_to_id {} does not exist in database for service id {}' \
        .format(reply_to_address.id, fake_uuid)


def test_check_service_email_reply_to_id_where_reply_to_id_is_not_found(sample_service, fake_uuid):
    with pytest.raises(BadRequestError) as e:
        check_service_email_reply_to_id(sample_service.id, fake_uuid, EMAIL_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == 'email_reply_to_id {} does not exist in database for service id {}' \
        .format(fake_uuid, sample_service.id)


@pytest.mark.parametrize('notification_type', ['sms', 'email', 'letter'])
def test_check_service_sms_sender_id_where_sms_sender_id_is_none(notification_type):
    assert check_service_sms_sender_id(None, None, notification_type) is None


def test_check_service_sms_sender_id_where_sms_sender_id_is_found(sample_service):
    sms_sender = create_service_sms_sender(service=sample_service, sms_sender='123456')
    assert check_service_sms_sender_id(sample_service.id, sms_sender.id, SMS_TYPE) == '123456'


def test_check_service_sms_sender_id_where_service_id_is_not_found(sample_service, fake_uuid):
    sms_sender = create_service_sms_sender(service=sample_service, sms_sender='123456')
    with pytest.raises(BadRequestError) as e:
        check_service_sms_sender_id(fake_uuid, sms_sender.id, SMS_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == 'sms_sender_id {} does not exist in database for service id {}' \
        .format(sms_sender.id, fake_uuid)


def test_check_service_sms_sender_id_where_sms_sender_is_not_found(sample_service, fake_uuid):
    with pytest.raises(BadRequestError) as e:
        check_service_sms_sender_id(sample_service.id, fake_uuid, SMS_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == 'sms_sender_id {} does not exist in database for service id {}' \
        .format(fake_uuid, sample_service.id)


def test_check_service_letter_contact_id_where_letter_contact_id_is_none():
    assert check_service_letter_contact_id(None, None, 'letter') is None


def test_check_service_letter_contact_id_where_letter_contact_id_is_found(sample_service):
    letter_contact = create_letter_contact(service=sample_service, contact_block='123456')
    assert check_service_letter_contact_id(sample_service.id, letter_contact.id, LETTER_TYPE) == '123456'


def test_check_service_letter_contact_id_where_service_id_is_not_found(sample_service, fake_uuid):
    letter_contact = create_letter_contact(service=sample_service, contact_block='123456')
    with pytest.raises(BadRequestError) as e:
        check_service_letter_contact_id(fake_uuid, letter_contact.id, LETTER_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == 'letter_contact_id {} does not exist in database for service id {}' \
        .format(letter_contact.id, fake_uuid)


def test_check_service_letter_contact_id_where_letter_contact_is_not_found(sample_service, fake_uuid):
    with pytest.raises(BadRequestError) as e:
        check_service_letter_contact_id(sample_service.id, fake_uuid, LETTER_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == 'letter_contact_id {} does not exist in database for service id {}' \
        .format(fake_uuid, sample_service.id)


@pytest.mark.parametrize('notification_type', ['sms', 'email', 'letter'])
def test_check_reply_to_with_empty_reply_to(sample_service, notification_type):
    assert check_reply_to(sample_service.id, None, notification_type) is None


def test_check_reply_to_email_type(sample_service):
    reply_to_address = create_reply_to_email(sample_service, "test@test.com")
    assert check_reply_to(sample_service.id, reply_to_address.id, EMAIL_TYPE) == 'test@test.com'


def test_check_reply_to_sms_type(sample_service):
    sms_sender = create_service_sms_sender(service=sample_service, sms_sender='123456')
    assert check_reply_to(sample_service.id, sms_sender.id, SMS_TYPE) == '123456'


def test_check_reply_to_letter_type(sample_service):
    letter_contact = create_letter_contact(service=sample_service, contact_block='123456')
    assert check_reply_to(sample_service.id, letter_contact.id, LETTER_TYPE) == '123456'


def test_check_if_service_can_send_files_by_email_raises_if_no_contact_link_set(sample_service):
    with pytest.raises(BadRequestError) as e:
        check_if_service_can_send_files_by_email(
            service_contact_link=sample_service.contact_link,
            service_id=sample_service.id
        )

    message = f"Send files by email has not been set up - add contact details for your service at " \
              f"http://localhost:6012/services/{sample_service.id}/service-settings/send-files-by-email"
    assert e.value.status_code == 400
    assert e.value.message == message


def test_check_if_service_can_send_files_by_email_passes_if_contact_link_set(sample_service):
    sample_service.contact_link = 'contact.me@gov.uk'
    check_if_service_can_send_files_by_email(
        service_contact_link=sample_service.contact_link,
        service_id=sample_service.id
    )
