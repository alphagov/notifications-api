from app.models import Notification, Job
from datetime import datetime
from app.dao.notifications_dao import (
    dao_create_notification,
    dao_update_notification,
    get_notification,
    get_notification_for_job,
    get_notifications_for_job
)
from tests.app.conftest import sample_job


def test_save_notification_and_increment_job(sample_template, sample_job):

    assert Notification.query.count() == 0
    data = {
        'to': '+44709123456',
        'job_id': sample_job.id,
        'service': sample_template.service,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['job_id'] == notification_from_db.job_id
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['created_at'] == notification_from_db.created_at
    assert 'sent' == notification_from_db.status
    assert Job.query.get(sample_job.id).notifications_sent == 1


def test_save_notification_and_increment_correct_job(notify_db, notify_db_session, sample_template):

    job_1 = sample_job(notify_db, notify_db_session, sample_template.service)
    job_2 = sample_job(notify_db, notify_db_session, sample_template.service)

    assert Notification.query.count() == 0
    data = {
        'to': '+44709123456',
        'job_id': job_1.id,
        'service': sample_template.service,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['job_id'] == notification_from_db.job_id
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['created_at'] == notification_from_db.created_at
    assert 'sent' == notification_from_db.status
    assert Job.query.get(job_1.id).notifications_sent == 1
    assert Job.query.get(job_2.id).notifications_sent == 0


def test_save_notification_with_no_job(sample_template):

    assert Notification.query.count() == 0
    data = {
        'to': '+44709123456',
        'service': sample_template.service,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['created_at'] == notification_from_db.created_at
    assert 'sent' == notification_from_db.status


def test_get_notification(sample_notification):
    notifcation_from_db = get_notification(
        sample_notification.service.id,
        sample_notification.id)
    assert sample_notification == notifcation_from_db


def test_save_notification_no_job_id(sample_template):

    assert Notification.query.count() == 0
    to = '+44709123456'
    data = {
        'to': to,
        'service': sample_template.service,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert 'sent' == notification_from_db.status


def test_get_notification_for_job(sample_notification):
    notifcation_from_db = get_notification_for_job(
        sample_notification.service.id,
        sample_notification.job_id,
        sample_notification.id)
    assert sample_notification == notifcation_from_db


def test_get_all_notifications_for_job(notify_db, notify_db_session, sample_job):

    from tests.app.conftest import sample_notification
    for i in range(0, 5):
        sample_notification(notify_db,
                            notify_db_session,
                            service=sample_job.service,
                            template=sample_job.template,
                            job=sample_job)

    notifcations_from_db = get_notifications_for_job(sample_job.service.id, sample_job.id).items
    assert len(notifcations_from_db) == 5


def test_update_notification(sample_notification):
    assert sample_notification.status == 'sent'
    sample_notification.status = 'failed'
    dao_update_notification(sample_notification)
    notification_from_db = Notification.query.get(sample_notification.id)
    assert notification_from_db.status == 'failed'
