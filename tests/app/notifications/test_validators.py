import pytest

from app.errors import InvalidRequest
from app.notifications.validators import check_service_message_limit, check_template_is_for_notification_type, \
    check_template_is_active
from tests.app.conftest import (sample_notification as create_notification,
                                sample_service as create_service)


@pytest.mark.parametrize('key_type', ['test', 'team', 'live'])
def test_check_service_message_limit_with_unrestricted_service_passes(key_type,
                                                                      sample_service,
                                                                      sample_notification):
    assert check_service_message_limit(key_type, sample_service) is None


@pytest.mark.parametrize('key_type', ['test', 'team', 'live'])
def test_check_service_message_limit_under_message_limit_passes(key_type,
                                                                sample_service,
                                                                sample_notification):
    assert check_service_message_limit(key_type, sample_service) is None


@pytest.mark.parametrize('key_type', ['team', 'live'])
def test_check_service_message_limit_over_message_limit_fails(key_type, notify_db, notify_db_session):
    service = create_service(notify_db, notify_db_session, restricted=True, limit=4)
    for x in range(5):
        create_notification(notify_db, notify_db_session, service=service)
    with pytest.raises(InvalidRequest):
        check_service_message_limit(key_type, service)


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
    with pytest.raises(InvalidRequest):
        check_template_is_for_notification_type(notification_type=notification_type,
                                                template_type=template_type)


def test_check_template_is_active_passes(sample_template):
    assert check_template_is_active(sample_template) is None


def test_check_template_is_active_passes(sample_template):
    sample_template.archived = True
    from app.dao.templates_dao import dao_update_template
    dao_update_template(sample_template)
    with pytest.raises(InvalidRequest):
        check_template_is_active(sample_template)
