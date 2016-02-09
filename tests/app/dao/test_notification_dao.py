import uuid

from app.models import Notification

from app.dao.notifications_dao import (
    save_notification,
    get_notification,
    get_notifications_by_job
)


def test_save_notification(notify_db, notify_db_session, sample_template, sample_job):

    assert Notification.query.count() == 0

    notification_id = uuid.uuid4()
    to = '+44709123456'
    job_id = sample_job.id
    data = {
        'id': notification_id,
        'to': to,
        'job_id': job_id,
        'service_id': sample_template.service.id,
        'template_id': sample_template.id
    }

    notification = Notification(**data)
    save_notification(notification)

    assert Notification.query.count() == 1

    notification_from_db = Notification.query.get(notification_id)

    assert data['id'] == notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['job_id'] == notification_from_db.job_id
    assert data['service_id'] == notification_from_db.service_id
    assert data['template_id'] == notification_from_db.template_id
    assert 'sent' == notification_from_db.status


def test_get_notification_for_job(notify_db, notify_db_session, sample_notification):
    notifcation_from_db = get_notification(sample_notification.job_id, sample_notification.id)
    assert sample_notification == notifcation_from_db


def test_get_all_notifications_for_job(notify_db, notify_db_session, sample_job):

    from tests.app.conftest import sample_notification
    for i in range(0, 5):
        sample_notification(notify_db,
                            notify_db_session,
                            service=sample_job.service,
                            template=sample_job.template,
                            job=sample_job)

    notifcations_from_db = get_notifications_by_job(sample_job.id)
    assert len(notifcations_from_db) == 5


def test_update_notification(notify_db, notify_db_session, sample_notification):
    assert sample_notification.status == 'sent'

    update_dict = {
        'id': sample_notification.id,
        'service_id': sample_notification.service_id,
        'template_id': sample_notification.template_id,
        'job': sample_notification.job,
        'status': 'failed'
    }

    save_notification(sample_notification, update_dict=update_dict)
    notification_from_db = Notification.query.get(sample_notification.id)
    assert notification_from_db.status == 'failed'
