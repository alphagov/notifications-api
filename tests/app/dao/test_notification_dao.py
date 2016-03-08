import pytest
import uuid
from freezegun import freeze_time
import random
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app.models import Notification, Job, ServiceNotificationStats
from datetime import datetime
from app.dao.notifications_dao import (
    dao_create_notification,
    dao_update_notification,
    get_notification,
    get_notification_for_job,
    get_notifications_for_job
)
from tests.app.conftest import sample_job


def test_save_notification_and_create_sms_stats(sample_template, sample_job):
    assert Notification.query.count() == 0
    data = {
        'to': '+44709123456',
        'job_id': sample_job.id,
        'service': sample_template.service,
        'service_id': sample_template.service.id,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

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

    stats = ServiceNotificationStats.query.filter(
        ServiceNotificationStats.service_id == sample_template.service.id
    ).first()

    assert stats.emails_requested == 0
    assert stats.sms_requested == 1


def test_save_notification_and_create_email_stats(sample_email_template, sample_job):
    assert Notification.query.count() == 0
    data = {
        'to': '+44709123456',
        'job_id': sample_job.id,
        'service': sample_email_template.service,
        'service_id': sample_email_template.service.id,
        'template': sample_email_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    dao_create_notification(notification, sample_email_template.template_type)

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

    stats = ServiceNotificationStats.query.filter(
        ServiceNotificationStats.service_id == sample_email_template.service.id
    ).first()

    assert stats.emails_requested == 1
    assert stats.sms_requested == 0


@freeze_time("2016-01-01 00:00:00.000000")
def test_save_notification_handles_midnight_properly(sample_template, sample_job):
    assert Notification.query.count() == 0
    data = {
        'to': '+44709123456',
        'job_id': sample_job.id,
        'service': sample_template.service,
        'service_id': sample_template.service.id,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    assert Notification.query.count() == 1

    stats = ServiceNotificationStats.query.filter(
        ServiceNotificationStats.service_id == sample_template.service.id
    ).first()

    assert stats.day == '2016-01-01'


@freeze_time("2016-01-01 23:59:59.999999")
def test_save_notification_handles_just_before_midnight_properly(sample_template, sample_job):
    assert Notification.query.count() == 0
    data = {
        'to': '+44709123456',
        'job_id': sample_job.id,
        'service': sample_template.service,
        'service_id': sample_template.service.id,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    assert Notification.query.count() == 1

    stats = ServiceNotificationStats.query.filter(
        ServiceNotificationStats.service_id == sample_template.service.id
    ).first()

    assert stats.day == '2016-01-01'


def test_save_notification_and_increment_email_stats(sample_email_template, sample_job):
    assert Notification.query.count() == 0
    data = {
        'to': '+44709123456',
        'job_id': sample_job.id,
        'service': sample_email_template.service,
        'service_id': sample_email_template.service.id,
        'template': sample_email_template,
        'created_at': datetime.utcnow()
    }

    notification_1 = Notification(**data)
    notification_2 = Notification(**data)
    dao_create_notification(notification_1, sample_email_template.template_type)

    assert Notification.query.count() == 1

    stats1 = ServiceNotificationStats.query.filter(
        ServiceNotificationStats.service_id == sample_email_template.service.id
    ).first()

    assert stats1.emails_requested == 1
    assert stats1.sms_requested == 0

    dao_create_notification(notification_2, sample_email_template)

    assert Notification.query.count() == 2

    stats2 = ServiceNotificationStats.query.filter(
        ServiceNotificationStats.service_id == sample_email_template.service.id
    ).first()

    assert stats2.emails_requested == 2
    assert stats2.sms_requested == 0


def test_save_notification_and_increment_sms_stats(sample_template, sample_job):
    assert Notification.query.count() == 0
    data = {
        'to': '+44709123456',
        'job_id': sample_job.id,
        'service': sample_template.service,
        'service_id': sample_template.service.id,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification_1 = Notification(**data)
    notification_2 = Notification(**data)
    dao_create_notification(notification_1, sample_template.template_type)

    assert Notification.query.count() == 1

    stats1 = ServiceNotificationStats.query.filter(
        ServiceNotificationStats.service_id == sample_template.service.id
    ).first()

    assert stats1.emails_requested == 0
    assert stats1.sms_requested == 1

    dao_create_notification(notification_2, sample_template.template_type)

    assert Notification.query.count() == 2

    stats2 = ServiceNotificationStats.query.filter(
        ServiceNotificationStats.service_id == sample_template.service.id
    ).first()

    assert stats2.emails_requested == 0
    assert stats2.sms_requested == 2


def test_not_save_notification_and_not_create_stats_on_commit_error(sample_template, sample_job):
    random_id = str(uuid.uuid4())

    assert Notification.query.count() == 0
    data = {
        'to': '+44709123456',
        'job_id': random_id,
        'service': sample_template.service,
        'service_id': sample_template.service.id,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    with pytest.raises(SQLAlchemyError):
        dao_create_notification(notification, sample_template.template_type)

    assert Notification.query.count() == 0
    assert Job.query.get(sample_job.id).notifications_sent == 0
    assert ServiceNotificationStats.query.count() == 0


def test_save_notification_and_increment_job(sample_template, sample_job):
    assert Notification.query.count() == 0
    data = {
        'to': '+44709123456',
        'job_id': sample_job.id,
        'service': sample_template.service,
        'service_id': sample_template.service.id,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

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

    notification_2 = Notification(**data)
    dao_create_notification(notification_2, sample_template)
    assert Notification.query.count() == 2
    assert Job.query.get(sample_job.id).notifications_sent == 2


def test_should_not_increment_job_if_notification_fails_to_persist(sample_template, sample_job):
    random_id = str(uuid.uuid4())

    assert Notification.query.count() == 0
    data = {
        'id': random_id,
        'to': '+44709123456',
        'job_id': sample_job.id,
        'service_id': sample_template.service.id,
        'service': sample_template.service,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification_1 = Notification(**data)
    dao_create_notification(notification_1, sample_template.template_type)

    assert Notification.query.count() == 1
    assert Job.query.get(sample_job.id).notifications_sent == 1
    job_last_updated_at = Job.query.get(sample_job.id).updated_at

    notification_2 = Notification(**data)
    with pytest.raises(SQLAlchemyError):
        dao_create_notification(notification_2, sample_template.template_type)

    assert Notification.query.count() == 1
    assert Job.query.get(sample_job.id).notifications_sent == 1
    assert Job.query.get(sample_job.id).updated_at == job_last_updated_at


def test_save_notification_and_increment_correct_job(notify_db, notify_db_session, sample_template):
    job_1 = sample_job(notify_db, notify_db_session, sample_template.service)
    job_2 = sample_job(notify_db, notify_db_session, sample_template.service)

    assert Notification.query.count() == 0
    data = {
        'to': '+44709123456',
        'job_id': job_1.id,
        'service_id': sample_template.service.id,
        'service': sample_template.service,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

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
        'service_id': sample_template.service.id,
        'service': sample_template.service,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

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
        'service_id': sample_template.service.id,
        'service': sample_template.service,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

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
        try:
            sample_notification(notify_db,
                                notify_db_session,
                                service=sample_job.service,
                                template=sample_job.template,
                                job=sample_job)
        except IntegrityError:
            pass

    notifcations_from_db = get_notifications_for_job(sample_job.service.id, sample_job.id).items
    assert len(notifcations_from_db) == 5
    stats = ServiceNotificationStats.query.filter(
        ServiceNotificationStats.service_id == sample_job.service.id
    ).first()

    assert stats.emails_requested == 0
    assert stats.sms_requested == 5


def test_update_notification(sample_notification, sample_template):
    assert sample_notification.status == 'sent'
    sample_notification.status = 'failed'
    dao_update_notification(sample_notification)
    notification_from_db = Notification.query.get(sample_notification.id)
    assert notification_from_db.status == 'failed'
