import datetime
import uuid

import pytest
from boto3.exceptions import Boto3Error
from sqlalchemy.exc import SQLAlchemyError
from freezegun import freeze_time
from collections import namedtuple

from app.models import Template, Notification, NotificationHistory
from app.notifications import SendNotificationToQueueError
from app.notifications.process_notifications import (create_content_for_notification,
                                                     persist_notification,
                                                     send_notification_to_queue,
                                                     simulated_recipient)
from app.utils import cache_key_for_service_template_counter
from app.v2.errors import BadRequestError


def test_create_content_for_notification_passes(sample_email_template):
    template = Template.query.get(sample_email_template.id)
    content = create_content_for_notification(template, None)
    assert str(content) == template.content


def test_create_content_for_notification_with_placeholders_passes(sample_template_with_placeholders):
    template = Template.query.get(sample_template_with_placeholders.id)
    content = create_content_for_notification(template, {'name': 'Bobby'})
    assert content.content == template.content
    assert 'Bobby' in str(content)


def test_create_content_for_notification_fails_with_missing_personalisation(sample_template_with_placeholders):
    template = Template.query.get(sample_template_with_placeholders.id)
    with pytest.raises(BadRequestError):
        create_content_for_notification(template, None)


def test_create_content_for_notification_allows_additional_personalisation(sample_template_with_placeholders):
    template = Template.query.get(sample_template_with_placeholders.id)
    create_content_for_notification(template, {'name': 'Bobby', 'Additional placeholder': 'Data'})


@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_creates_and_save_to_db(sample_template, sample_api_key, sample_job, mocker):
    mocked_redis = mocker.patch('app.notifications.process_notifications.redis_store.get')

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0
    notification = persist_notification(sample_template.id, sample_template.version, '+447111111111',
                                        sample_template.service, {}, 'sms', sample_api_key.id,
                                        sample_api_key.key_type, job_id=sample_job.id,
                                        job_row_number=100, reference="ref")

    assert Notification.query.get(notification.id) is not None
    assert NotificationHistory.query.get(notification.id) is not None

    notification_from_db = Notification.query.one()
    notification_history_from_db = NotificationHistory.query.one()

    assert notification_from_db.id == notification_history_from_db.id
    assert notification_from_db.template_id == notification_history_from_db.template_id
    assert notification_from_db.template_version == notification_history_from_db.template_version
    assert notification_from_db.api_key_id == notification_history_from_db.api_key_id
    assert notification_from_db.key_type == notification_history_from_db.key_type
    assert notification_from_db.key_type == notification_history_from_db.key_type
    assert notification_from_db.billable_units == notification_history_from_db.billable_units
    assert notification_from_db.notification_type == notification_history_from_db.notification_type
    assert notification_from_db.created_at == notification_history_from_db.created_at
    assert not notification_from_db.sent_at
    assert not notification_history_from_db.sent_at
    assert notification_from_db.updated_at == notification_history_from_db.updated_at
    assert notification_from_db.status == notification_history_from_db.status
    assert notification_from_db.reference == notification_history_from_db.reference
    assert notification_from_db.client_reference == notification_history_from_db.client_reference

    mocked_redis.assert_called_once_with(str(sample_template.service_id) + "-2016-01-01-count")


@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_does_not_create_and_save_to_db_if_persist_is_false(
        sample_template, sample_api_key, sample_job, mocker
):
    mocked_redis = mocker.patch('app.notifications.process_notifications.redis_store.get')

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0
    persist_notification(
        sample_template.id,
        sample_template.version,
        '+447111111111',
        sample_template.service,
        {},
        'sms',
        sample_api_key.id,
        sample_api_key.key_type,
        job_id=sample_job.id,
        job_row_number=100,
        reference="ref",
        persist=False)

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0

    mocked_redis.assert_called_once_with(str(sample_template.service_id) + "-2016-01-01-count")


def test_persist_notification_throws_exception_when_missing_template(sample_api_key):
    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0
    with pytest.raises(SQLAlchemyError):
        persist_notification(template_id=None,
                             template_version=None,
                             recipient='+447111111111',
                             service=sample_api_key.service,
                             personalisation=None,
                             notification_type='sms',
                             api_key_id=sample_api_key.id,
                             key_type=sample_api_key.key_type)
    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0


def test_exception_thown_by_redis_store_get_should_not_be_fatal(sample_template, sample_api_key, mocker):
    mocker.patch(
        'app.notifications.process_notifications.redis_store.redis_store.incr',
        side_effect=Exception("broken redis"))

    notification = persist_notification(
        sample_template.id,
        sample_template.version,
        '+447111111111',
        sample_template.service,
        {},
        'sms',
        sample_api_key.id,
        sample_api_key.key_type)
    assert Notification.query.count() == 1
    assert Notification.query.get(notification.id) is not None
    assert NotificationHistory.query.count() == 1


def test_cache_is_not_incremented_on_failure_to_persist_notification(sample_api_key, mocker):
    mocked_redis = mocker.patch('app.redis_store.get')
    mock_service_template_cache = mocker.patch('app.redis_store.get_all_from_hash')
    with pytest.raises(SQLAlchemyError):
        persist_notification(template_id=None,
                             template_version=None,
                             recipient='+447111111111',
                             service=sample_api_key.service,
                             personalisation=None,
                             notification_type='sms',
                             api_key_id=sample_api_key.id,
                             key_type=sample_api_key.key_type)
    mocked_redis.assert_not_called()
    mock_service_template_cache.assert_not_called()


@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_with_optionals(sample_job, sample_api_key, mocker):
    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0
    mocked_redis = mocker.patch('app.notifications.process_notifications.redis_store.get')
    mock_service_template_cache = mocker.patch(
        'app.notifications.process_notifications.redis_store.get_all_from_hash')
    n_id = uuid.uuid4()
    created_at = datetime.datetime(2016, 11, 11, 16, 8, 18)
    persist_notification(template_id=sample_job.template.id,
                         template_version=sample_job.template.version,
                         recipient='+447111111111',
                         service=sample_job.service,
                         personalisation=None, notification_type='sms',
                         api_key_id=sample_api_key.id,
                         key_type=sample_api_key.key_type,
                         created_at=created_at,
                         job_id=sample_job.id,
                         job_row_number=10,
                         reference="ref from client",
                         notification_id=n_id)
    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 1
    persisted_notification = Notification.query.all()[0]
    assert persisted_notification.id == n_id
    persisted_notification.job_id == sample_job.id
    assert persisted_notification.job_row_number == 10
    assert persisted_notification.created_at == created_at
    mocked_redis.assert_called_once_with(str(sample_job.service_id) + "-2016-01-01-count")
    mock_service_template_cache.assert_called_once_with(cache_key_for_service_template_counter(sample_job.service_id))
    assert persisted_notification.client_reference == "ref from client"
    assert persisted_notification.reference is None


@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_increments_cache_if_key_exists(sample_template, sample_api_key, mocker):
    mock_incr = mocker.patch('app.notifications.process_notifications.redis_store.incr')
    mock_incr_hash_value = mocker.patch('app.notifications.process_notifications.redis_store.increment_hash_value')

    persist_notification(sample_template.id, sample_template.version, '+447111111111',
                         sample_template.service, {}, 'sms', sample_api_key.id,
                         sample_api_key.key_type, reference="ref")
    mock_incr.assert_not_called()
    mock_incr_hash_value.assert_not_called()

    mocker.patch('app.notifications.process_notifications.redis_store.get', return_value=1)
    mocker.patch('app.notifications.process_notifications.redis_store.get_all_from_hash',
                 return_value={sample_template.id, 1})
    persist_notification(sample_template.id, sample_template.version, '+447111111122',
                         sample_template.service, {}, 'sms', sample_api_key.id,
                         sample_api_key.key_type, reference="ref2")
    mock_incr.assert_called_once_with(str(sample_template.service_id) + "-2016-01-01-count", )
    mock_incr_hash_value.assert_called_once_with(cache_key_for_service_template_counter(sample_template.service_id),
                                                 sample_template.id)


@pytest.mark.parametrize('research_mode, requested_queue, expected_queue, notification_type, key_type',
                         [(True, None, 'research-mode', 'sms', 'normal'),
                          (True, None, 'research-mode', 'email', 'normal'),
                          (True, None, 'research-mode', 'email', 'team'),
                          (False, None, 'send-sms', 'sms', 'normal'),
                          (False, None, 'send-email', 'email', 'normal'),
                          (False, None, 'send-sms', 'sms', 'team'),
                          (False, None, 'research-mode', 'sms', 'test'),
                          (True, 'notify', 'research-mode', 'email', 'normal'),
                          (False, 'notify', 'notify', 'sms', 'normal'),
                          (False, 'notify', 'notify', 'email', 'normal'),
                          (False, 'notify', 'research-mode', 'sms', 'test')])
def test_send_notification_to_queue(notify_db, notify_db_session,
                                    research_mode, requested_queue, expected_queue,
                                    notification_type, key_type, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(notification_type))
    Notification = namedtuple('Notification', ['id', 'key_type', 'notification_type', 'created_at'])
    notification = Notification(
        id=uuid.uuid4(),
        key_type=key_type,
        notification_type=notification_type,
        created_at=datetime.datetime(2016, 11, 11, 16, 8, 18),
    )

    send_notification_to_queue(notification=notification, research_mode=research_mode, queue=requested_queue)

    mocked.assert_called_once_with([str(notification.id)], queue=expected_queue)


def test_send_notification_to_queue_throws_exception_deletes_notification(sample_notification, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async', side_effect=Boto3Error("EXPECTED"))
    with pytest.raises(SendNotificationToQueueError):
        send_notification_to_queue(sample_notification, False)
        mocked.assert_called_once_with([(str(sample_notification.id))], queue='send-sms')

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0


@pytest.mark.parametrize("to_address, notification_type, expected",
                         [("+447700900000", "sms", True),
                          ("+447700900111", "sms", True),
                          ("+447700900222", "sms", True),
                          ("simulate-delivered@notifications.service.gov.uk", "email", True),
                          ("simulate-delivered-2@notifications.service.gov.uk", "email", True),
                          ("simulate-delivered-3@notifications.service.gov.uk", "email", True),
                          ("07515896969", "sms", False),
                          ("valid_email@test.com", "email", False)])
def test_simulated_recipient(notify_api, to_address, notification_type, expected):
    # The values where the expected = 'research-mode' are listed in the config['SIMULATED_EMAIL_ADDRESSES']
    # and config['SIMULATED_SMS_NUMBERS']. These values should result in using the research mode queue.
    #  SIMULATED_EMAIL_ADDRESSES = ('simulate-delivered@notifications.service.gov.uk',
    #                               'simulate-delivered-2@notifications.service.gov.uk',
    #                               'simulate-delivered-2@notifications.service.gov.uk')
    #  SIMULATED_SMS_NUMBERS = ('+447700900000', '+447700900111', '+447700900222')

    actual = simulated_recipient(to_address, notification_type)
    assert actual == expected
