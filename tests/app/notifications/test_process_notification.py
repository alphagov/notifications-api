import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.errors import InvalidRequest
from app.models import Template, Notification, NotificationHistory
from app.notifications.process_notifications import (create_content_for_notification,
                                                     persist_notification, send_notification_to_queue)
from app.v2.errors import BadRequestError
from tests.app.conftest import sample_notification, sample_template, sample_email_template


def test_create_content_for_notification_passes(sample_email_template):
    template = Template.query.get(sample_email_template.id)
    content = create_content_for_notification(template, None)
    assert content.content == template.content


def test_create_content_for_notification_fails_with_missing_personalisation(sample_template_with_placeholders):
    template = Template.query.get(sample_template_with_placeholders.id)
    with pytest.raises(BadRequestError):
        create_content_for_notification(template, None)


def test_persist_notification_creates_and_save_to_db(sample_template, sample_api_key):
    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0
    notification = persist_notification(sample_template.id, sample_template.version, '+447111111111',
                                        sample_template.service.id, {}, 'sms', sample_api_key.id,
                                        sample_api_key.key_type)
    assert Notification.query.count() == 1
    assert Notification.query.get(notification.id).__eq__(notification)
    assert NotificationHistory.query.count() == 1


def test_persist_notification_throws_exception_when_missing_template(sample_template, sample_api_key):
    assert Notification.query.count() == 0
    with pytest.raises(SQLAlchemyError):
        persist_notification(template_id=None,
                             template_version=None,
                             recipient='+447111111111',
                             service_id=sample_template.service.id,
                             personalisation=None, notification_type='sms',
                             api_key_id=sample_api_key.id,
                             key_type=sample_api_key.key_type)


@pytest.mark.parametrize('research_mode, queue, notification_type, key_type',
                         [(True, 'research-mode', 'sms', 'normal'),
                          (False, 'send-sms', 'sms', 'normal'),
                          (True, 'research-mode', 'email', 'normal'),
                          (False, 'send-email', 'email', 'normal'),
                          (False, 'research-mode', 'sms', 'test')])
def test_send_notification_to_queue(notify_db, notify_db_session,
                                    research_mode, notification_type,
                                    queue, key_type, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(notification_type))
    template = sample_template(notify_db, notify_db_session) if notification_type == 'sms' \
        else sample_email_template(notify_db, notify_db_session)
    notification = sample_notification(notify_db, notify_db_session, template=template, key_type=key_type)
    send_notification_to_queue(notification=notification, research_mode=research_mode)

    mocked.assert_called_once_with([str(notification.id)], queue=queue)


def test_send_notification_to_queue(sample_notification, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async', side_effect=Exception("EXPECTED"))
    with pytest.raises(InvalidRequest):
        send_notification_to_queue(sample_notification, False)
        mocked.assert_called_once_with([(str(sample_notification.id))], queue='send-sms')
