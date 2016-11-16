import datetime

import pytest
from boto3.exceptions import Boto3Error
from sqlalchemy.exc import SQLAlchemyError

from app.models import Template, Notification, NotificationHistory
from app.notifications.process_notifications import (create_content_for_notification,
                                                     persist_notification, send_notification_to_queue)
from app.v2.errors import BadRequestError
from tests.app.conftest import sample_notification, sample_template, sample_email_template


def test_create_content_for_notification_passes(sample_email_template):
    template = Template.query.get(sample_email_template.id)
    content = create_content_for_notification(template, None)
    assert content.replaced == template.content


def test_create_content_for_notification_with_placeholders_passes(sample_template_with_placeholders):
    template = Template.query.get(sample_template_with_placeholders.id)
    content = create_content_for_notification(template, {'name': 'Bobby'})
    assert content.content == template.content
    assert 'Bobby' in content.replaced


def test_create_content_for_notification_fails_with_missing_personalisation(sample_template_with_placeholders):
    template = Template.query.get(sample_template_with_placeholders.id)
    with pytest.raises(BadRequestError):
        create_content_for_notification(template, None)


def test_create_content_for_notification_fails_with_additional_personalisation(sample_template_with_placeholders):
    template = Template.query.get(sample_template_with_placeholders.id)
    with pytest.raises(BadRequestError) as e:
        create_content_for_notification(template, {'name': 'Bobby', 'Additional placeholder': 'Data'})
    assert e.value.message == 'Template personalisation not needed for template: Additional placeholder'


def test_persist_notification_creates_and_save_to_db(sample_template, sample_api_key):
    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0
    notification = persist_notification(sample_template.id, sample_template.version, '+447111111111',
                                        sample_template.service.id, {}, 'sms', sample_api_key.id,
                                        sample_api_key.key_type)
    assert Notification.query.count() == 1
    assert Notification.query.get(notification.id) is not None
    assert NotificationHistory.query.count() == 1


def test_persist_notification_throws_exception_when_missing_template(sample_api_key):
    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0
    with pytest.raises(SQLAlchemyError):
        persist_notification(template_id=None,
                             template_version=None,
                             recipient='+447111111111',
                             service_id=sample_api_key.service_id,
                             personalisation=None,
                             notification_type='sms',
                             api_key_id=sample_api_key.id,
                             key_type=sample_api_key.key_type)
    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0


def test_persist_notification_with_job_and_created(sample_job, sample_api_key):
    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0
    created_at = datetime.datetime(2016, 11, 11, 16, 8, 18)
    persist_notification(template_id=sample_job.template.id,
                         template_version=sample_job.template.version,
                         recipient='+447111111111',
                         service_id=sample_job.service.id,
                         personalisation=None, notification_type='sms',
                         api_key_id=sample_api_key.id,
                         key_type=sample_api_key.key_type,
                         created_at=created_at,
                         job_id=sample_job.id,
                         job_row_number=10)
    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 1
    persisted_notification = Notification.query.all()[0]
    assert persisted_notification.job_id == sample_job.id
    assert persisted_notification.job_row_number == 10
    assert persisted_notification.created_at == created_at


@pytest.mark.parametrize('research_mode, queue, notification_type, key_type',
                         [(True, 'research-mode', 'sms', 'normal'),
                          (True, 'research-mode', 'email', 'normal'),
                          (True, 'research-mode', 'email', 'team'),
                          (False, 'send-sms', 'sms', 'normal'),
                          (False, 'send-email', 'email', 'normal'),
                          (False, 'send-sms', 'sms', 'team'),
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


def test_send_notification_to_queue_throws_exception_deletes_notification(sample_notification, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async', side_effect=Boto3Error("EXPECTED"))
    with pytest.raises(Boto3Error):
        send_notification_to_queue(sample_notification, False)
        mocked.assert_called_once_with([(str(sample_notification.id))], queue='send-sms')

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0
