import pytest
import uuid
from app import (
    DATE_FORMAT
)
from freezegun import freeze_time
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app.models import Notification, Job, NotificationStatistics
from datetime import datetime, timedelta
from app.dao.notifications_dao import (
    dao_create_notification,
    dao_update_notification,
    get_notification,
    get_notification_for_job,
    get_notifications_for_job,
    dao_get_notification_statistics_for_service,
    delete_successful_notifications_created_more_than_a_day_ago,
    delete_failed_notifications_created_more_than_a_week_ago,
    dao_get_notification_statistics_for_service_and_day,
    update_notification_status_by_id,
    update_notification_reference_by_id,
    update_notification_status_by_reference
)
from tests.app.conftest import sample_job
from tests.app.conftest import sample_notification


def test_should_by_able_to_update_reference_by_id(sample_notification):
    assert not Notification.query.get(sample_notification.id).reference
    count = update_notification_reference_by_id(sample_notification.id, 'reference')
    assert count == 1
    assert Notification.query.get(sample_notification.id).reference == 'reference'


def test_should_by_able_to_update_status_by_reference(sample_notification):
    assert Notification.query.get(sample_notification.id).status == "sent"
    update_notification_reference_by_id(sample_notification.id, 'reference')
    update_notification_status_by_reference('reference', 'delivered')
    assert Notification.query.get(sample_notification.id).status == 'delivered'


def test_should_by_able_to_update_status_by_id(sample_notification):
    assert Notification.query.get(sample_notification.id).status == 'sent'
    count = update_notification_status_by_id(sample_notification.id, 'delivered')
    assert count == 1
    assert Notification.query.get(sample_notification.id).status == 'delivered'


def test_should_return_zero_count_if_no_notification_with_id():
    assert update_notification_status_by_id(str(uuid.uuid4()), 'delivered') == 0


def test_should_return_zero_count_if_no_notification_with_reference():
    assert update_notification_status_by_reference('something', 'delivered') == 0


def test_should_be_able_to_get_statistics_for_a_service(sample_template):
    data = {
        'to': '+44709123456',
        'service': sample_template.service,
        'service_id': sample_template.service.id,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    stats = dao_get_notification_statistics_for_service(sample_template.service.id)
    assert len(stats) == 1
    assert stats[0].emails_requested == 0
    assert stats[0].sms_requested == 1
    assert stats[0].sms_delivered == 0
    assert stats[0].sms_error == 0
    assert stats[0].day == notification.created_at.strftime(DATE_FORMAT)
    assert stats[0].service_id == notification.service_id
    assert stats[0].emails_requested == 0
    assert stats[0].emails_delivered == 0
    assert stats[0].emails_error == 0


def test_should_be_able_to_get_statistics_for_a_service_for_a_day(sample_template):
    now = datetime.utcnow()
    data = {
        'to': '+44709123456',
        'service': sample_template.service,
        'service_id': sample_template.service.id,
        'template': sample_template,
        'created_at': now
    }

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)
    stat = dao_get_notification_statistics_for_service_and_day(
        sample_template.service.id, now.strftime(DATE_FORMAT)
    )
    assert stat.emails_requested == 0
    assert stat.emails_error == 0
    assert stat.emails_delivered == 0
    assert stat.sms_requested == 1
    assert stat.sms_error == 0
    assert stat.sms_delivered == 0
    assert stat.day == notification.created_at.strftime(DATE_FORMAT)
    assert stat.service_id == notification.service_id


def test_should_return_none_if_no_statistics_for_a_service_for_a_day(sample_template):
    now = datetime.utcnow()
    data = {
        'to': '+44709123456',
        'service': sample_template.service,
        'service_id': sample_template.service.id,
        'template': sample_template,
        'created_at': now
    }

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)
    assert not dao_get_notification_statistics_for_service_and_day(
        sample_template.service.id, (datetime.utcnow() - timedelta(days=1)).strftime(DATE_FORMAT)
    )


def test_should_be_able_to_get_all_statistics_for_a_service(sample_template):
    data = {
        'to': '+44709123456',
        'service': sample_template.service,
        'service_id': sample_template.service.id,
        'template': sample_template,
        'created_at': datetime.utcnow()
    }

    notification_1 = Notification(**data)
    notification_2 = Notification(**data)
    notification_3 = Notification(**data)
    dao_create_notification(notification_1, sample_template.template_type)
    dao_create_notification(notification_2, sample_template.template_type)
    dao_create_notification(notification_3, sample_template.template_type)

    stats = dao_get_notification_statistics_for_service(sample_template.service.id)
    assert len(stats) == 1
    assert stats[0].emails_requested == 0
    assert stats[0].sms_requested == 3


def test_should_be_able_to_get_all_statistics_for_a_service_for_several_days(sample_template):
    data = {
        'to': '+44709123456',
        'service': sample_template.service,
        'service_id': sample_template.service.id,
        'template': sample_template
    }

    today = datetime.utcnow()
    yesterday = datetime.utcnow() - timedelta(days=1)
    two_days_ago = datetime.utcnow() - timedelta(days=2)
    data.update({
        'created_at': today
    })
    notification_1 = Notification(**data)
    data.update({
        'created_at': yesterday
    })
    notification_2 = Notification(**data)
    data.update({
        'created_at': two_days_ago
    })
    notification_3 = Notification(**data)
    dao_create_notification(notification_1, sample_template.template_type)
    dao_create_notification(notification_2, sample_template.template_type)
    dao_create_notification(notification_3, sample_template.template_type)

    stats = dao_get_notification_statistics_for_service(sample_template.service.id)
    assert len(stats) == 3
    assert stats[0].emails_requested == 0
    assert stats[0].sms_requested == 1
    assert stats[0].day == today.strftime(DATE_FORMAT)
    assert stats[1].emails_requested == 0
    assert stats[1].sms_requested == 1
    assert stats[1].day == yesterday.strftime(DATE_FORMAT)
    assert stats[2].emails_requested == 0
    assert stats[2].sms_requested == 1
    assert stats[2].day == two_days_ago.strftime(DATE_FORMAT)


def test_should_be_empty_list_if_no_statistics_for_a_service(sample_service):
    assert len(dao_get_notification_statistics_for_service(sample_service.id)) == 0


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

    stats = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_template.service.id
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

    stats = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_email_template.service.id
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

    stats = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_template.service.id
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

    stats = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_template.service.id
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

    stats1 = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_email_template.service.id
    ).first()

    assert stats1.emails_requested == 1
    assert stats1.sms_requested == 0

    dao_create_notification(notification_2, sample_email_template)

    assert Notification.query.count() == 2

    stats2 = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_email_template.service.id
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

    stats1 = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_template.service.id
    ).first()

    assert stats1.emails_requested == 0
    assert stats1.sms_requested == 1

    dao_create_notification(notification_2, sample_template.template_type)

    assert Notification.query.count() == 2

    stats2 = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_template.service.id
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
    assert NotificationStatistics.query.count() == 0


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
    stats = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_job.service.id
    ).first()

    assert stats.emails_requested == 0
    assert stats.sms_requested == 5


def test_update_notification(sample_notification, sample_template):
    assert sample_notification.status == 'sent'
    sample_notification.status = 'failed'
    dao_update_notification(sample_notification)
    notification_from_db = Notification.query.get(sample_notification.id)
    assert notification_from_db.status == 'failed'


def test_should_delete_sent_notifications_after_one_day(notify_db, notify_db_session):
    created_at = datetime.utcnow() - timedelta(hours=24)
    sample_notification(notify_db, notify_db_session, created_at=created_at)
    sample_notification(notify_db, notify_db_session, created_at=created_at)
    assert len(Notification.query.all()) == 2
    delete_successful_notifications_created_more_than_a_day_ago()
    assert len(Notification.query.all()) == 0


def test_should_delete_failed_notifications_after_seven_days(notify_db, notify_db_session):
    created_at = datetime.utcnow() - timedelta(hours=24 * 7)
    sample_notification(notify_db, notify_db_session, created_at=created_at, status="failed")
    sample_notification(notify_db, notify_db_session, created_at=created_at, status="failed")
    assert len(Notification.query.all()) == 2
    delete_failed_notifications_created_more_than_a_week_ago()
    assert len(Notification.query.all()) == 0


def test_should_not_delete_sent_notifications_before_one_day(notify_db, notify_db_session):
    expired = datetime.utcnow() - timedelta(hours=24)
    valid = datetime.utcnow() - timedelta(hours=23, minutes=59, seconds=59)
    sample_notification(notify_db, notify_db_session, created_at=expired, to_field="expired")
    sample_notification(notify_db, notify_db_session, created_at=valid, to_field="valid")

    assert len(Notification.query.all()) == 2
    delete_successful_notifications_created_more_than_a_day_ago()
    assert len(Notification.query.all()) == 1
    assert Notification.query.first().to == 'valid'


def test_should_not_delete_failed_notifications_before_seven_days(notify_db, notify_db_session):
    expired = datetime.utcnow() - timedelta(hours=24 * 7)
    valid = datetime.utcnow() - timedelta(hours=(24 * 6) + 23, minutes=59, seconds=59)
    sample_notification(notify_db, notify_db_session, created_at=expired, status="failed", to_field="expired")
    sample_notification(notify_db, notify_db_session, created_at=valid, status="failed", to_field="valid")
    assert len(Notification.query.all()) == 2
    delete_failed_notifications_created_more_than_a_week_ago()
    assert len(Notification.query.all()) == 1
    assert Notification.query.first().to == 'valid'
