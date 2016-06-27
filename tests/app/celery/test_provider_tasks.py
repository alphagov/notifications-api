from datetime import datetime

from celery.exceptions import MaxRetriesExceededError
from mock import ANY, call
from notifications_utils.recipients import validate_phone_number, format_phone_number

import app
from app import statsd_client, mmg_client
from app.celery import provider_tasks
from app.celery.provider_tasks import send_sms_to_provider
from app.celery.research_mode_tasks import send_sms_response
from app.celery.tasks import provider_to_use
from app.clients.sms import SmsClientException
from app.dao import notifications_dao, provider_details_dao
from app.dao import provider_statistics_dao
from app.models import Notification, NotificationStatistics, Job
from tests.app.conftest import (
    sample_notification
)


def test_should_by_10_second_delay_as_default():
    assert provider_tasks.retry_iteration_to_delay() == 10


def test_should_by_10_second_delay_on_unmapped_retry_iteration():
    assert provider_tasks.retry_iteration_to_delay(99) == 10


def test_should_by_10_second_delay_on_retry_one():
    assert provider_tasks.retry_iteration_to_delay(0) == 10


def test_should_by_1_minute_delay_on_retry_two():
    assert provider_tasks.retry_iteration_to_delay(1) == 60


def test_should_by_5_minute_delay_on_retry_two():
    assert provider_tasks.retry_iteration_to_delay(2) == 300


def test_should_by_60_minute_delay_on_retry_two():
    assert provider_tasks.retry_iteration_to_delay(3) == 3600


def test_should_by_240_minute_delay_on_retry_two():
    assert provider_tasks.retry_iteration_to_delay(4) == 14400


def test_should_return_highest_priority_active_provider(notify_db, notify_db_session):
    providers = provider_details_dao.get_provider_details_by_notification_type('sms')
    first = providers[0]
    second = providers[1]

    assert provider_to_use('sms', '1234').name == first.identifier

    first.priority = 20
    second.priority = 10

    provider_details_dao.dao_update_provider_details(first)
    provider_details_dao.dao_update_provider_details(second)

    assert provider_to_use('sms', '1234').name == second.identifier

    first.priority = 10
    first.active = False
    second.priority = 20

    provider_details_dao.dao_update_provider_details(first)
    provider_details_dao.dao_update_provider_details(second)

    assert provider_to_use('sms', '1234').name == second.identifier

    first.active = True
    provider_details_dao.dao_update_provider_details(first)

    assert provider_to_use('sms', '1234').name == first.identifier


def test_should_send_personalised_template_to_correct_sms_provider_and_persist(
        notify_db,
        notify_db_session,
        sample_template_with_placeholders,
        mocker):
    db_notification = sample_notification(notify_db, notify_db_session, template=sample_template_with_placeholders,
                                          to_field="+447234123123", personalisation={"name": "Jo"},
                                          status='created')

    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.statsd_client.incr')
    mocker.patch('app.statsd_client.timing_with_dates')
    mocker.patch('app.statsd_client.timing')

    send_sms_to_provider(
        db_notification.service_id,
        db_notification.id
    )

    mmg_client.send_sms.assert_called_once_with(
        to=format_phone_number(validate_phone_number("+447234123123")),
        content="Sample service: Hello Jo",
        reference=str(db_notification.id)
    )
    notification = Notification.query.filter_by(id=db_notification.id).one()

    assert notification.status == 'sending'
    assert notification.sent_at <= datetime.utcnow()
    assert notification.sent_by == 'mmg'
    assert notification.content_char_count == 24
    assert notification.personalisation == {"name": "Jo"}


def test_send_sms_should_use_template_version_from_notification_not_latest(
        notify_db,
        notify_db_session,
        sample_template,
        mocker):
    db_notification = sample_notification(notify_db, notify_db_session,
                                          template=sample_template, to_field='+447234123123',
                                          status='created')

    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    version_on_notification = sample_template.version

    # Change the template
    from app.dao.templates_dao import dao_update_template, dao_get_template_by_id
    sample_template.content = sample_template.content + " another version of the template"
    dao_update_template(sample_template)
    t = dao_get_template_by_id(sample_template.id)
    assert t.version > version_on_notification

    send_sms_to_provider(
        db_notification.service_id,
        db_notification.id
    )

    mmg_client.send_sms.assert_called_once_with(
        to=format_phone_number(validate_phone_number("+447234123123")),
        content="Sample service: This is a template",
        reference=str(db_notification.id)
    )

    persisted_notification = notifications_dao.get_notification(sample_template.service_id, db_notification.id)
    assert persisted_notification.to == db_notification.to
    assert persisted_notification.template_id == sample_template.id
    assert persisted_notification.template_version == version_on_notification
    assert persisted_notification.template_version != sample_template.version
    assert persisted_notification.content_char_count == len("Sample service: This is a template")
    assert persisted_notification.status == 'sending'
    assert not persisted_notification.personalisation


def test_should_call_send_sms_response_task_if_research_mode(notify_db, sample_service, sample_notification, mocker):

    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.celery.research_mode_tasks.send_sms_response.apply_async')

    sample_service.research_mode = True
    notify_db.session.add(sample_service)
    notify_db.session.commit()

    send_sms_to_provider(
        sample_notification.service_id,
        sample_notification.id
    )
    assert not mmg_client.send_sms.called
    send_sms_response.apply_async.assert_called_once_with(
        ('mmg', str(sample_notification.id), sample_notification.to), queue='research-mode'
    )

    persisted_notification = notifications_dao.get_notification(sample_service.id, sample_notification.id)
    assert persisted_notification.to == sample_notification.to
    assert persisted_notification.template_id == sample_notification.template_id
    assert persisted_notification.status == 'sending'
    assert persisted_notification.sent_at <= datetime.utcnow()
    assert persisted_notification.sent_by == 'mmg'
    assert not persisted_notification.personalisation


def test_should_update_provider_stats_on_success(notify_db, sample_service, sample_notification, mocker):
    provider_stats = provider_statistics_dao.get_provider_statistics(sample_service).all()
    assert len(provider_stats) == 0

    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.celery.research_mode_tasks.send_sms_response.apply_async')

    send_sms_to_provider(
        sample_notification.service_id,
        sample_notification.id
    )

    updated_provider_stats = provider_statistics_dao.get_provider_statistics(sample_service).all()
    assert updated_provider_stats[0].provider.identifier == 'mmg'
    assert updated_provider_stats[0].unit_count == 1


def test_not_should_update_provider_stats_on_success_in_research_mode(notify_db, sample_service, sample_notification,
                                                                      mocker):
    provider_stats = provider_statistics_dao.get_provider_statistics(sample_service).all()
    assert len(provider_stats) == 0

    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.celery.research_mode_tasks.send_sms_response.apply_async')

    sample_service.research_mode = True
    notify_db.session.add(sample_service)
    notify_db.session.commit()

    send_sms_to_provider(
        sample_notification.service_id,
        sample_notification.id
    )

    updated_provider_stats = provider_statistics_dao.get_provider_statistics(sample_service).all()
    assert len(updated_provider_stats) == 0


def test_should_not_send_to_provider_when_status_is_not_created(notify_db, notify_db_session,
                                                                sample_service,
                                                                mocker):
    notification = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                       service=sample_service,
                                       status='sending')
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.celery.research_mode_tasks.send_sms_response.apply_async')

    send_sms_to_provider(
        notification.service_id,
        notification.id
    )

    app.mmg_client.send_sms.assert_not_called()
    app.celery.research_mode_tasks.send_sms_response.apply_async.assert_not_called()


def test_statsd_updates(notify_db, notify_db_session, sample_service, sample_notification, mocker):
    mocker.patch('app.statsd_client.incr')
    mocker.patch('app.statsd_client.timing')
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.celery.research_mode_tasks.send_sms_response.apply_async')

    send_sms_to_provider(
        sample_notification.service_id,
        sample_notification.id
    )

    statsd_client.incr.assert_called_once_with("notifications.tasks.send-sms-to-provider")
    statsd_client.timing.assert_has_calls([
        call("notifications.tasks.send-sms-to-provider.task-time", ANY),
        call("notifications.sms.total-time", ANY)
    ])


def test_should_go_into_technical_error_if_exceeds_retries(
        notify_db,
        notify_db_session,
        sample_service,
        mocker):

    notification = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                       service=sample_service, status='created')

    mocker.patch('app.statsd_client.incr')
    mocker.patch('app.statsd_client.timing')
    mocker.patch('app.mmg_client.send_sms', side_effect=SmsClientException("EXPECTED"))
    mocker.patch('app.celery.provider_tasks.send_sms_to_provider.retry', side_effect=MaxRetriesExceededError())

    send_sms_to_provider(
        notification.service_id,
        notification.id
    )

    provider_tasks.send_sms_to_provider.retry.assert_called_with(queue='retry', countdown=10)
    assert statsd_client.incr.assert_not_called
    assert statsd_client.timing.assert_not_called

    db_notification = Notification.query.filter_by(id=notification.id).one()
    assert db_notification.status == 'technical-failure'
    notification_stats = NotificationStatistics.query.filter_by(service_id=notification.service.id).first()
    assert notification_stats.sms_requested == 1
    assert notification_stats.sms_failed == 1
    job = Job.query.get(notification.job.id)
    assert job.notification_count == 1
    assert job.notifications_failed == 1
