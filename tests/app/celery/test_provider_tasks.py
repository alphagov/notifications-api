import uuid

from mock import ANY, call

from app import statsd_client, mmg_client
from app.celery.provider_tasks import send_sms_to_provider
from app.celery.tasks import provider_to_use
from app.dao import provider_statistics_dao
from datetime import datetime
from freezegun import freeze_time
from app.dao import notifications_dao, provider_details_dao
from notifications_utils.recipients import validate_phone_number, format_phone_number
from app.celery.research_mode_tasks import send_sms_response

from tests.app.conftest import (
    sample_notification
)


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
    db_notification = sample_notification(notify_db, notify_db_session, template=sample_template_with_placeholders)

    notification = _notification_json(
        sample_template_with_placeholders,
        to="+447234123123",
        personalisation={"name": "Jo"}
    )
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.statsd_client.incr')
    mocker.patch('app.statsd_client.timing_with_dates')
    mocker.patch('app.statsd_client.timing')

    freezer = freeze_time("2016-01-01 11:09:00.00000")
    freezer.start()
    now = datetime.utcnow()
    freezer.stop()

    freezer = freeze_time("2016-01-01 11:10:00.00000")
    freezer.start()

    send_sms_to_provider(
        db_notification.service_id,
        db_notification.id,
        "encrypted-in-reality"
    )
    freezer.stop()

    mmg_client.send_sms.assert_called_once_with(
        to=format_phone_number(validate_phone_number("+447234123123")),
        content="Sample service: Hello Jo",
        reference=str(db_notification.id)
    )

    statsd_client.incr.assert_called_once_with("notifications.tasks.send-sms-to-provider")
    statsd_client.timing.assert_has_calls([
        call("notifications.tasks.send-sms-to-provider.task-time", ANY),
        call("notifications.sms.total-time", ANY)
    ])

    notification = notifications_dao.get_notification(
        db_notification.service_id, db_notification.id
    )

    assert notification.status == 'sending'
    assert notification.sent_at > now
    assert notification.sent_by == 'mmg'


def test_should_send_template_to_correct_sms_provider_and_persist(
        notify_db,
        notify_db_session,
        sample_template,
        mocker):
    db_notification = sample_notification(notify_db, notify_db_session, template=sample_template)

    notification = _notification_json(
        sample_template,
        to="+447234123123"
    )
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.statsd_client.incr')
    mocker.patch('app.statsd_client.timing_with_dates')
    mocker.patch('app.statsd_client.timing')

    freezer = freeze_time("2016-01-01 11:09:00.00000")
    freezer.start()
    now = datetime.utcnow()
    freezer.stop()

    freezer = freeze_time("2016-01-01 11:10:00.00000")
    freezer.start()

    send_sms_to_provider(
        db_notification.service_id,
        db_notification.id,
        "encrypted-in-reality"
    )
    freezer.stop()

    mmg_client.send_sms.assert_called_once_with(
        to=format_phone_number(validate_phone_number("+447234123123")),
        content="Sample service: This is a template",
        reference=str(db_notification.id)
    )


def test_send_sms_should_use_template_version_from_notification_not_latest(
        notify_db,
        notify_db_session,
        sample_template,
        mocker):
    db_notification = sample_notification(notify_db, notify_db_session, template=sample_template)

    notification = _notification_json(sample_template, '+447234123123')
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    version_on_notification = sample_template.version

    # Change the template
    from app.dao.templates_dao import dao_update_template, dao_get_template_by_id
    sample_template.content = sample_template.content + " another version of the template"
    dao_update_template(sample_template)
    t = dao_get_template_by_id(sample_template.id)
    assert t.version > version_on_notification

    now = datetime.utcnow()

    send_sms_to_provider(
        db_notification.service_id,
        db_notification.id,
        "encrypted-in-reality"
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
    assert persisted_notification.sent_at > now
    assert persisted_notification.status == 'sending'
    assert persisted_notification.sent_by == 'mmg'
    assert persisted_notification.content_char_count == len("Sample service: This is a template")


def test_should_call_send_sms_response_task_if_research_mode(notify_db, sample_service, sample_notification, mocker):
    notification = _notification_json(
        sample_notification.template,
        to=sample_notification.to
    )
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.celery.research_mode_tasks.send_sms_response.apply_async')

    sample_service.research_mode = True
    notify_db.session.add(sample_service)
    notify_db.session.commit()

    now = datetime.utcnow()
    send_sms_to_provider(
        sample_notification.service_id,
        sample_notification.id,
        "encrypted-in-reality"
    )
    assert not mmg_client.send_sms.called
    send_sms_response.apply_async.assert_called_once_with(
        ('mmg', str(sample_notification.id), sample_notification.to), queue='research-mode'
    )

    persisted_notification = notifications_dao.get_notification(sample_service.id, sample_notification.id)
    assert persisted_notification.to == sample_notification.to
    assert persisted_notification.template_id == sample_notification.template_id
    assert persisted_notification.status == 'sending'
    assert persisted_notification.sent_at > now
    assert persisted_notification.sent_by == 'mmg'


def test_should_update_provider_stats_on_success(notify_db, sample_service, sample_notification, mocker):
    provider_stats = provider_statistics_dao.get_provider_statistics(sample_service).all()
    assert len(provider_stats) == 0

    notification = _notification_json(
        sample_notification.template,
        to=sample_notification.to
    )
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.celery.research_mode_tasks.send_sms_response.apply_async')

    send_sms_to_provider(
        sample_notification.service_id,
        sample_notification.id,
        "encrypted-in-reality"
    )

    updated_provider_stats = provider_statistics_dao.get_provider_statistics(sample_service).all()
    assert updated_provider_stats[0].provider.identifier == 'mmg'
    assert updated_provider_stats[0].unit_count == 1


def test_not_should_update_provider_stats_on_success(notify_db, sample_service, sample_notification, mocker):
    provider_stats = provider_statistics_dao.get_provider_statistics(sample_service).all()
    assert len(provider_stats) == 0

    notification = _notification_json(
        sample_notification.template,
        to=sample_notification.to
    )
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.celery.research_mode_tasks.send_sms_response.apply_async')

    sample_service.research_mode = True
    notify_db.session.add(sample_service)
    notify_db.session.commit()

    send_sms_to_provider(
        sample_notification.service_id,
        sample_notification.id,
        "encrypted-in-reality"
    )

    updated_provider_stats = provider_statistics_dao.get_provider_statistics(sample_service).all()
    assert len(updated_provider_stats) == 0


def test_statsd_updates(notify_db, notify_db_session, sample_service, sample_notification, mocker):
    notification = _notification_json(
        sample_notification.template,
        to=sample_notification.to
    )

    mocker.patch('app.statsd_client.incr')
    mocker.patch('app.statsd_client.timing')
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.celery.research_mode_tasks.send_sms_response.apply_async')

    send_sms_to_provider(
        sample_notification.service_id,
        sample_notification.id,
        "encrypted-in-reality"
    )

    statsd_client.incr.assert_called_once_with("notifications.tasks.send-sms-to-provider")
    statsd_client.timing.assert_has_calls([
        call("notifications.tasks.send-sms-to-provider.task-time", ANY),
        call("notifications.sms.total-time", ANY)
    ])


def _notification_json(template, to, personalisation=None, job_id=None, row_number=None):
    notification = {
        "template": template.id,
        "template_version": template.version,
        "to": to,
    }
    if personalisation:
        notification.update({"personalisation": personalisation})
    if job_id:
        notification.update({"job": job_id})
    if row_number:
        notification['row_number'] = row_number
    return notification
