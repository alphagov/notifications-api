import pytest
from freezegun import freeze_time
from flask import current_app
import app
from app.models import INTERNATIONAL_SMS_TYPE, SMS_TYPE, EMAIL_TYPE
from app.notifications.validators import (
    check_service_over_daily_message_limit,
    check_template_is_for_notification_type,
    check_template_is_active,
    service_can_send_to_recipient,
    check_sms_content_char_count,
    check_service_over_api_rate_limit,
    validate_and_format_recipient,
    check_service_email_reply_to_id
)

from app.v2.errors import (
    BadRequestError,
    TooManyRequestsError,
    RateLimitError)
from tests.app.conftest import (
    sample_notification as create_notification,
    sample_service as create_service,
    sample_service_whitelist,
    sample_api_key)


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
        notify_db,
        notify_db_session,
        sample_service,
        mocker
):
    with freeze_time("2016-01-01 12:00:00.000000"):
        for x in range(5):
            create_notification(notify_db, notify_db_session, service=sample_service)
        mocker.patch('app.notifications.validators.redis_store.get', return_value=None)
        mocker.patch('app.notifications.validators.redis_store.set')
        check_service_over_daily_message_limit(key_type, sample_service)
        app.notifications.validators.redis_store.set.assert_called_with(
            str(sample_service.id) + "-2016-01-01-count", 5, ex=3600
        )


@pytest.mark.parametrize('key_type', ['team', 'normal'])
def test_check_service_message_limit_over_message_limit_fails(key_type, notify_db, notify_db_session, mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):
        mocker.patch('app.redis_store.get', return_value=None)
        mocker.patch('app.notifications.validators.redis_store.set')

        service = create_service(notify_db, notify_db_session, restricted=True, limit=4)
        for x in range(5):
            create_notification(notify_db, notify_db_session, service=service)
        with pytest.raises(TooManyRequestsError) as e:
            check_service_over_daily_message_limit(key_type, service)
        assert e.value.status_code == 429
        assert e.value.message == 'Exceeded send limits (4) for today'
        assert e.value.fields == []
        app.notifications.validators.redis_store.set.assert_called_with(
            str(service.id) + "-2016-01-01-count", 5, ex=3600
        )


@pytest.mark.parametrize('key_type', ['team', 'normal'])
def test_check_service_message_limit_in_cache_over_message_limit_fails(
        notify_db,
        notify_db_session,
        key_type,
        mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):
        mocker.patch('app.redis_store.get', return_value=5)
        mocker.patch('app.notifications.validators.redis_store.set')
        mocker.patch('app.notifications.validators.services_dao')

        service = create_service(notify_db, notify_db_session, restricted=True, limit=4)
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
def test_service_can_send_to_recipient_passes(key_type, notify_db, notify_db_session):
    trial_mode_service = create_service(notify_db, notify_db_session, service_name='trial mode', restricted=True)
    assert service_can_send_to_recipient(trial_mode_service.users[0].email_address,
                                         key_type,
                                         trial_mode_service) is None
    assert service_can_send_to_recipient(trial_mode_service.users[0].mobile_number,
                                         key_type,
                                         trial_mode_service) is None


@pytest.mark.parametrize('key_type',
                         ['test', 'normal'])
def test_service_can_send_to_recipient_passes_for_live_service_non_team_member(key_type, notify_db, notify_db_session):
    live_service = create_service(notify_db, notify_db_session, service_name='live', restricted=False)
    assert service_can_send_to_recipient("some_other_email@test.com",
                                         key_type,
                                         live_service) is None
    assert service_can_send_to_recipient('07513332413',
                                         key_type,
                                         live_service) is None


def test_service_can_send_to_recipient_passes_for_whitelisted_recipient_passes(notify_db, notify_db_session,
                                                                               sample_service):
    sample_service_whitelist(notify_db, notify_db_session, email_address="some_other_email@test.com")
    assert service_can_send_to_recipient("some_other_email@test.com",
                                         'team',
                                         sample_service) is None
    sample_service_whitelist(notify_db, notify_db_session, mobile_number='07513332413')
    assert service_can_send_to_recipient('07513332413',
                                         'team',
                                         sample_service) is None


@pytest.mark.parametrize('recipient', ['07513332413', 'some_other_email@test.com'])
@pytest.mark.parametrize('key_type, error_message',
                         [('team', 'Can’t send to this recipient using a team-only API key'),
                          ('normal',
                           "Can’t send to this recipient when service is in trial mode – see https://www.notifications.service.gov.uk/trial-mode")])  # noqa
def test_service_can_send_to_recipient_fails_when_recipient_is_not_on_team(recipient, key_type, error_message,
                                                                           notify_db, notify_db_session):
    trial_mode_service = create_service(notify_db, notify_db_session, service_name='trial mode', restricted=True)
    with pytest.raises(BadRequestError) as exec_info:
        service_can_send_to_recipient(recipient,
                                      key_type,
                                      trial_mode_service)
    assert exec_info.value.status_code == 400
    assert exec_info.value.message == error_message
    assert exec_info.value.fields == []


def test_service_can_send_to_recipient_fails_when_mobile_number_is_not_on_team(notify_db, notify_db_session):
    live_service = create_service(notify_db, notify_db_session, service_name='live mode', restricted=False)
    with pytest.raises(BadRequestError) as e:
        service_can_send_to_recipient("0758964221",
                                      'team',
                                      live_service)
    assert e.value.status_code == 400
    assert e.value.message == 'Can’t send to this recipient using a team-only API key'
    assert e.value.fields == []


@pytest.mark.parametrize('char_count', [495, 0, 494, 200])
def test_check_sms_content_char_count_passes(char_count, notify_api):
    assert check_sms_content_char_count(char_count) is None


@pytest.mark.parametrize('char_count', [496, 500, 6000])
def test_check_sms_content_char_count_fails(char_count, notify_api):
    with pytest.raises(BadRequestError) as e:
        check_sms_content_char_count(char_count)
    assert e.value.status_code == 400
    assert e.value.message == 'Content for template has a character count greater than the limit of {}'.format(
        notify_api.config['SMS_CHAR_COUNT_LIMIT'])
    assert e.value.fields == []


@pytest.mark.parametrize('key_type, limit, interval', [('team', 1, 2), ('live', 10, 20), ('test', 100, 200)])
def test_that_when_exceed_rate_limit_request_fails(
        notify_db,
        notify_db_session,
        key_type,
        limit,
        interval,
        mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):

        if key_type == 'live':
            api_key_type = 'normal'
        else:
            api_key_type = key_type

        mocker.patch('app.redis_store.exceeded_rate_limit', return_value=True)
        mocker.patch('app.notifications.validators.services_dao')

        service = create_service(notify_db, notify_db_session, restricted=True)
        api_key = sample_api_key(notify_db, notify_db_session, service=service, key_type=api_key_type)
        with pytest.raises(RateLimitError) as e:
            check_service_over_api_rate_limit(service, api_key)

        assert app.redis_store.exceeded_rate_limit.called_with(
            "{}-{}".format(str(service.id), api_key.key_type),
            limit,
            interval
        )
        assert e.value.status_code == 429
        assert e.value.message == 'Exceeded rate limit for key type {} of {} requests per {} seconds'.format(
            key_type.upper(), limit, interval
        )
        assert e.value.fields == []


@pytest.mark.parametrize('key_type, limit, interval', [('team', 1, 2), ('normal', 10, 20), ('test', 100, 200)])
def test_that_when_not_exceeded_rate_limit_request_succeeds(
        notify_db,
        notify_db_session,
        key_type,
        limit,
        interval,
        mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):
        mocker.patch('app.redis_store.exceeded_rate_limit', return_value=False)
        mocker.patch('app.notifications.validators.services_dao')

        service = create_service(notify_db, notify_db_session, restricted=True)
        api_key = sample_api_key(notify_db, notify_db_session, service=service, key_type=key_type)

        check_service_over_api_rate_limit(service, api_key)
        assert app.redis_store.exceeded_rate_limit.called_with(
            "{}-{}".format(str(service.id), api_key.key_type),
            limit,
            interval
        )


def test_should_not_rate_limit_if_limiting_is_disabled(
        notify_db,
        notify_db_session,
        mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):
        current_app.config['API_RATE_LIMIT_ENABLED'] = False

        mocker.patch('app.redis_store.exceeded_rate_limit', return_value=False)
        mocker.patch('app.notifications.validators.services_dao')

        service = create_service(notify_db, notify_db_session, restricted=True)
        api_key = sample_api_key(notify_db, notify_db_session, service=service)

        check_service_over_api_rate_limit(service, api_key)
        assert not app.redis_store.exceeded_rate_limit.called


@pytest.mark.parametrize('key_type', ['test', 'normal'])
def test_rejects_api_calls_with_international_numbers_if_service_does_not_allow_int_sms(sample_service, key_type):
    with pytest.raises(BadRequestError) as e:
        validate_and_format_recipient('20-12-1234-1234', key_type, sample_service, SMS_TYPE)
    assert e.value.status_code == 400
    assert e.value.message == 'Cannot send to international mobile numbers'
    assert e.value.fields == []


@pytest.mark.parametrize('key_type', ['test', 'normal'])
def test_allows_api_calls_with_international_numbers_if_service_does_allow_int_sms(
        key_type, notify_db, notify_db_session):
    service = create_service(notify_db, notify_db_session, permissions=[SMS_TYPE, INTERNATIONAL_SMS_TYPE])
    result = validate_and_format_recipient('20-12-1234-1234', key_type, service, SMS_TYPE)
    assert result == '201212341234'


@pytest.mark.parametrize('key_type', ['test', 'normal'])
def test_check_service_email_reply_to_id_where_reply_to_id_is_none(
        key_type, notify_db, notify_db_session):
    assert check_service_email_reply_to_id(None, None) is None


@pytest.mark.parametrize('key_type', ['test', 'normal'])
def test_check_service_email_reply_to_id_where_reply_to_id_is_not_found(key_type, notify_db, notify_db_session):
    service = create_service(notify_db, notify_db_session, permissions=[EMAIL_TYPE])
    with pytest.raises(BadRequestError) as e:
        check_service_email_reply_to_id(service.id, 1)
    assert e.value.status_code == 400
    assert e.value.message == 'reply_to_id does not exist in database'
