import pytest
from app.notifications.validators import check_service_message_limit, check_template_is_for_notification_type, \
    check_template_is_active, service_can_send_to_recipient, check_sms_content_char_count
from app.v2.errors import BadRequestError, TooManyRequestsError
from tests.app.conftest import (sample_notification as create_notification,
                                sample_service as create_service, sample_service_whitelist)


@pytest.mark.parametrize('key_type', ['test', 'team', 'normal'])
def test_check_service_message_limit_with_unrestricted_service_passes(key_type,
                                                                      sample_service,
                                                                      sample_notification):
    assert check_service_message_limit(key_type, sample_service) is None


@pytest.mark.parametrize('key_type', ['test', 'team', 'normal'])
def test_check_service_message_limit_under_message_limit_passes(key_type,
                                                                sample_service,
                                                                sample_notification):
    assert check_service_message_limit(key_type, sample_service) is None


@pytest.mark.parametrize('key_type', ['team', 'normal'])
def test_check_service_message_limit_over_message_limit_fails(key_type, notify_db, notify_db_session):
    service = create_service(notify_db, notify_db_session, restricted=True, limit=4)
    for x in range(5):
        create_notification(notify_db, notify_db_session, service=service)
    with pytest.raises(TooManyRequestsError) as e:
        check_service_message_limit(key_type, service)
    assert e.value.status_code == 429
    assert e.value.code == '10429'
    assert e.value.message == 'Exceeded send limits (4) for today'
    assert e.value.fields == []


@pytest.mark.parametrize('template_type, notification_type',
                         [('email', 'email'),
                          ('sms', 'sms')])
def test_check_template_is_for_notification_type_pass(template_type, notification_type):
    assert check_template_is_for_notification_type(notification_type=notification_type,
                                                   template_type=template_type) is None


@pytest.mark.parametrize('template_type, notification_type',
                         [('sms', 'email'),
                          ('email', 'sms')])
def test_check_template_is_for_notification_type_fails_when_template_type_does_not_match_notification_type(
        template_type, notification_type):
    with pytest.raises(BadRequestError) as e:
        check_template_is_for_notification_type(notification_type=notification_type,
                                                template_type=template_type)
    assert e.value.code == 10400
    error_message = '{0} template is not suitable for {1} notification'.format(template_type, notification_type)
    assert e.value.message == error_message
    assert e.value.link == 'link to documentation'
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
    assert e.value.code == 10400
    assert e.value.message == 'Template has been deleted'
    assert e.value.link == "link to documentation"
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


@pytest.mark.parametrize('key_type',
                         ['team'])
def test_service_can_send_to_recipient_passes_for_whitelisted_recipient_passes(key_type, notify_db, notify_db_session,
                                                                               sample_service):
    sample_service_whitelist(notify_db, notify_db_session, email_address="some_other_email@test.com")
    assert service_can_send_to_recipient("some_other_email@test.com",
                                         key_type,
                                         sample_service) is None
    sample_service_whitelist(notify_db, notify_db_session, mobile_number='07513332413')
    assert service_can_send_to_recipient('07513332413',
                                         key_type,
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
        assert service_can_send_to_recipient(recipient,
                                             key_type,
                                             trial_mode_service) is None
    assert exec_info.value.status_code == 400
    assert exec_info.value.code == 10400
    assert exec_info.value.message == error_message
    assert exec_info.value.link == 'link to documentation'
    assert exec_info.value.fields == []


def test_service_can_send_to_recipient_fails_when_mobile_number_is_not_on_team(notify_db, notify_db_session):
    live_service = create_service(notify_db, notify_db_session, service_name='live mode', restricted=False)
    with pytest.raises(BadRequestError) as e:
        assert service_can_send_to_recipient("0758964221",
                                             'team',
                                             live_service) is None
    assert e.value.status_code == 400
    assert e.value.code == 10400
    assert e.value.message == 'Can’t send to this recipient using a team-only API key'
    assert e.value.link == 'link to documentation'
    assert e.value.fields == []


@pytest.mark.parametrize('char_count', [495, 0, 494, 200])
def test_check_sms_content_char_count_passes(char_count, notify_api):
    assert check_sms_content_char_count(char_count) is None


@pytest.mark.parametrize('char_count', [496, 500, 6000])
def test_check_sms_content_char_count_fails(char_count, notify_api):
    with pytest.raises(BadRequestError) as e:
        check_sms_content_char_count(char_count)
    assert e.value.status_code == 400
    assert e.value.code == 10400
    assert e.value.message == 'Content for template has a character count greater than the limit of {}'.format(
        notify_api.config['SMS_CHAR_COUNT_LIMIT'])
    assert e.value.link == 'link to documentation'
    assert e.value.fields == []
