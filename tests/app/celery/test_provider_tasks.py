import uuid

from mock import ANY

from app import statsd_client, mmg_client, DATETIME_FORMAT
from app.celery.provider_tasks import send_sms_to_provider
from app.celery.tasks import provider_to_use
from app.dao import provider_details_dao
from datetime import datetime, timedelta
from freezegun import freeze_time
from app.dao import notifications_dao, jobs_dao, provider_details_dao
from notifications_utils.recipients import validate_phone_number, format_phone_number

from tests.app.conftest import (
    sample_service,
    sample_user,
    sample_template,
    sample_job,
    sample_email_template,
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


def test_should_send_template_to_correct_sms_provider_and_persist(sample_notification, sample_template_with_placeholders, mocker):
    notification = _notification_json(
        sample_template_with_placeholders,
        to="+447234123123",
        personalisation={"name": "Jo"}
    )
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.dao.notifications_dao.get_notification_by_id', return_value=sample_notification)
    mocker.patch('app.mmg_client.send_sms')
    mocker.patch('app.mmg_client.get_name', return_value="mmg")
    mocker.patch('app.statsd_client.incr')
    mocker.patch('app.statsd_client.timing_with_dates')
    mocker.patch('app.statsd_client.timing')

    notification_id = uuid.uuid4()

    freezer = freeze_time("2016-01-01 11:09:00.00000")
    freezer.start()
    now = datetime.utcnow()
    freezer.stop()

    freezer = freeze_time("2016-01-01 11:10:00.00000")
    freezer.start()

    send_sms_to_provider(
        sample_template_with_placeholders.service_id,
        notification_id,
        "encrypted-in-reality"
    )
    freezer.stop()


    mmg_client.send_sms.assert_called_once_with(
        to=format_phone_number(validate_phone_number("+447234123123")),
        content="Sample service: Hello Jo",
        reference=str(notification_id)
    )

    statsd_client.incr.assert_called_once_with("notifications.tasks.send-sms")
    statsd_client.timing.assert_called_once_with("notifications.tasks.send-sms-to-provider.task-time", ANY)
    statsd_client.timing.assert_called_once_with("notifications.sms.total-time", ANY)


    notification = notifications_dao.get_notification(
        sample_template_with_placeholders.service_id, notification_id
    )
    assert notification.status == 'sending'
    assert notification.sent_at > now
    assert notification.sent_by == 'mmg'


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