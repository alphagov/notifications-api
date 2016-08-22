from datetime import datetime, timedelta, date
import uuid
from functools import partial

import pytest

from freezegun import freeze_time
from mock import ANY
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app import db

from app.models import (
    Notification,
    NotificationHistory,
    Job,
    NotificationStatistics,
    TemplateStatistics,
    NOTIFICATION_STATUS_TYPES,
    KEY_TYPE_NORMAL
)

from app.dao.notifications_dao import (
    dao_create_notification,
    dao_update_notification,
    get_notification,
    get_notification_for_job,
    get_notifications_for_job,
    dao_get_notification_statistics_for_service,
    delete_notifications_created_more_than_a_week_ago,
    dao_get_notification_statistics_for_service_and_day,
    update_notification_status_by_id,
    update_provider_stats,
    update_notification_status_by_reference,
    dao_get_template_statistics_for_service,
    get_notifications_for_service, dao_get_7_day_agg_notification_statistics_for_service,
    dao_get_potential_notification_statistics_for_day, dao_get_notification_statistics_for_day,
    dao_get_template_statistics_for_template, get_notification_by_id, dao_get_template_usage)

from notifications_utils.template import get_sms_fragment_count

from tests.app.conftest import (sample_notification, sample_template, sample_email_template, sample_service)


def test_should_have_decorated_notifications_dao_functions():
    assert dao_get_notification_statistics_for_service.__wrapped__.__name__ == 'dao_get_notification_statistics_for_service'  # noqa
    assert dao_get_template_usage.__wrapped__.__name__ == 'dao_get_template_usage'  # noqa
    assert dao_get_notification_statistics_for_service_and_day.__wrapped__.__name__ == 'dao_get_notification_statistics_for_service_and_day'  # noqa
    assert dao_get_notification_statistics_for_day.__wrapped__.__name__ == 'dao_get_notification_statistics_for_day'  # noqa
    assert dao_get_potential_notification_statistics_for_day.__wrapped__.__name__ == 'dao_get_potential_notification_statistics_for_day'  # noqa
    assert dao_get_7_day_agg_notification_statistics_for_service.__wrapped__.__name__ == 'dao_get_7_day_agg_notification_statistics_for_service'  # noqa
    assert dao_get_template_statistics_for_service.__wrapped__.__name__ == 'dao_get_template_statistics_for_service'  # noqa
    assert dao_get_template_statistics_for_template.__wrapped__.__name__ == 'dao_get_template_statistics_for_template'  # noqa
    assert dao_create_notification.__wrapped__.__name__ == 'dao_create_notification'  # noqa
    assert update_notification_status_by_id.__wrapped__.__name__ == 'update_notification_status_by_id'  # noqa
    assert dao_update_notification.__wrapped__.__name__ == 'dao_update_notification'  # noqa
    assert update_provider_stats.__wrapped__.__name__ == 'update_provider_stats'  # noqa
    assert update_notification_status_by_reference.__wrapped__.__name__ == 'update_notification_status_by_reference'  # noqa
    assert get_notification_for_job.__wrapped__.__name__ == 'get_notification_for_job'  # noqa
    assert get_notifications_for_job.__wrapped__.__name__ == 'get_notifications_for_job'  # noqa
    assert get_notification.__wrapped__.__name__ == 'get_notification'  # noqa
    assert get_notifications_for_service.__wrapped__.__name__ == 'get_notifications_for_service'  # noqa
    assert get_notification_by_id.__wrapped__.__name__ == 'get_notification_by_id'  # noqa
    assert delete_notifications_created_more_than_a_week_ago.__wrapped__.__name__ == 'delete_notifications_created_more_than_a_week_ago'  # noqa


def test_should_by_able_to_get_template_count_from_notifications_history(notify_db, notify_db_session, sample_service):
    sms = sample_template(notify_db, notify_db_session)
    email = sample_email_template(notify_db, notify_db_session)
    sample_notification(notify_db, notify_db_session, service=sample_service, template=sms)
    sample_notification(notify_db, notify_db_session, service=sample_service, template=sms)
    sample_notification(notify_db, notify_db_session, service=sample_service, template=sms)
    sample_notification(notify_db, notify_db_session, service=sample_service, template=email)
    sample_notification(notify_db, notify_db_session, service=sample_service, template=email)

    results = dao_get_template_usage(sample_service.id)
    assert results[0].name == 'Email Template Name'
    assert results[0].template_type == 'email'
    assert results[0].count == 2

    assert results[1].name == 'Template Name'
    assert results[1].template_type == 'sms'
    assert results[1].count == 3


def test_should_by_able_to_get_template_count_from_notifications_history_for_service(
        notify_db,
        notify_db_session):
    service_1 = sample_service(notify_db, notify_db_session, service_name="test1", email_from="test1")
    service_2 = sample_service(notify_db, notify_db_session, service_name="test2", email_from="test2")
    service_3 = sample_service(notify_db, notify_db_session, service_name="test3", email_from="test3")

    sms = sample_template(notify_db, notify_db_session)

    sample_notification(notify_db, notify_db_session, service=service_1, template=sms)
    sample_notification(notify_db, notify_db_session, service=service_1, template=sms)
    sample_notification(notify_db, notify_db_session, service=service_2, template=sms)

    assert dao_get_template_usage(service_1.id)[0].count == 2
    assert dao_get_template_usage(service_2.id)[0].count == 1
    assert len(dao_get_template_usage(service_3.id)) == 0


def test_should_by_able_to_get_zero_count_from_notifications_history_if_no_rows(sample_service):
    results = dao_get_template_usage(sample_service.id)
    assert len(results) == 0


def test_should_by_able_to_get_zero_count_from_notifications_history_if_no_service():
    results = dao_get_template_usage(str(uuid.uuid4()))
    assert len(results) == 0


def test_should_by_able_to_get_template_count_from_notifications_history_across_days(
        notify_db,
        notify_db_session,
        sample_service):
    sms = sample_template(notify_db, notify_db_session)
    email = sample_email_template(notify_db, notify_db_session)

    today = datetime.now()
    yesterday = datetime.now() - timedelta(days=1)
    one_month_ago = datetime.now() - timedelta(days=30)

    sample_notification(notify_db, notify_db_session, created_at=today, service=sample_service, template=email)
    sample_notification(notify_db, notify_db_session, created_at=today, service=sample_service, template=email)
    sample_notification(notify_db, notify_db_session, created_at=today, service=sample_service, template=sms)

    sample_notification(notify_db, notify_db_session, created_at=yesterday, service=sample_service, template=email)
    sample_notification(notify_db, notify_db_session, created_at=yesterday, service=sample_service, template=email)
    sample_notification(notify_db, notify_db_session, created_at=yesterday, service=sample_service, template=email)
    sample_notification(notify_db, notify_db_session, created_at=yesterday, service=sample_service, template=sms)

    sample_notification(notify_db, notify_db_session, created_at=one_month_ago, service=sample_service, template=sms)
    sample_notification(notify_db, notify_db_session, created_at=one_month_ago, service=sample_service, template=sms)
    sample_notification(notify_db, notify_db_session, created_at=one_month_ago, service=sample_service, template=sms)

    results = dao_get_template_usage(sample_service.id)

    assert len(results) == 2

    assert [(row.name, row.template_type, row.count) for row in results] == [
        ('Email Template Name', 'email', 5),
        ('Template Name', 'sms', 5)
    ]


def test_should_by_able_to_get_template_count_from_notifications_history_with_day_limit(
        notify_db,
        notify_db_session,
        sample_service):
    sms = sample_template(notify_db, notify_db_session)

    email = sample_email_template(notify_db, notify_db_session)

    today = datetime.now()
    yesterday = datetime.now() - timedelta(days=1)
    one_month_ago = datetime.now() - timedelta(days=30)

    sample_notification(notify_db, notify_db_session, created_at=today, service=sample_service, template=email)
    sample_notification(notify_db, notify_db_session, created_at=today, service=sample_service, template=email)
    sample_notification(notify_db, notify_db_session, created_at=today, service=sample_service, template=sms)

    sample_notification(notify_db, notify_db_session, created_at=yesterday, service=sample_service, template=email)
    sample_notification(notify_db, notify_db_session, created_at=yesterday, service=sample_service, template=email)
    sample_notification(notify_db, notify_db_session, created_at=yesterday, service=sample_service, template=email)
    sample_notification(notify_db, notify_db_session, created_at=yesterday, service=sample_service, template=sms)

    sample_notification(notify_db, notify_db_session, created_at=one_month_ago, service=sample_service, template=sms)
    sample_notification(notify_db, notify_db_session, created_at=one_month_ago, service=sample_service, template=sms)
    sample_notification(notify_db, notify_db_session, created_at=one_month_ago, service=sample_service, template=sms)

    results_day_one = dao_get_template_usage(sample_service.id, limit_days=0)
    assert len(results_day_one) == 2

    results_day_two = dao_get_template_usage(sample_service.id, limit_days=1)
    assert len(results_day_two) == 2

    results_day_30 = dao_get_template_usage(sample_service.id, limit_days=31)
    assert len(results_day_30) == 2

    assert [(row.name, row.template_type, row.count) for row in results_day_one] == [
        ('Email Template Name', 'email', 2),
        ('Template Name', 'sms', 1)
    ]

    assert [(row.name, row.template_type, row.count) for row in results_day_two] == [
        ('Email Template Name', 'email', 5),
        ('Template Name', 'sms', 2),
    ]

    assert [(row.name, row.template_type, row.count) for row in results_day_30] == [
        ('Email Template Name', 'email', 5),
        ('Template Name', 'sms', 5),
    ]


def test_should_by_able_to_update_status_by_reference(sample_email_template, ses_provider):
    data = _notification_json(sample_email_template, status='sending')

    notification = Notification(**data)
    dao_create_notification(
        notification,
        sample_email_template.template_type)

    assert Notification.query.get(notification.id).status == "sending"
    notification.reference = 'reference'
    dao_update_notification(notification)

    update_notification_status_by_reference('reference', 'delivered', 'delivered')
    assert Notification.query.get(notification.id).status == 'delivered'
    _assert_notification_stats(notification.service_id, emails_delivered=1, emails_requested=1, emails_failed=0)


def test_should_by_able_to_update_status_by_id(sample_template, sample_job, mmg_provider):
    with freeze_time('2000-01-01 12:00:00'):
        data = _notification_json(sample_template, job_id=sample_job.id, status='sending')
        notification = Notification(**data)
        dao_create_notification(notification, sample_template.template_type)

    assert Notification.query.get(notification.id).status == 'sending'

    with freeze_time('2000-01-02 12:00:00'):
        assert update_notification_status_by_id(notification.id, 'delivered', 'delivered')

    assert Notification.query.get(notification.id).status == 'delivered'
    _assert_notification_stats(notification.service_id, sms_delivered=1, sms_requested=1, sms_failed=0)
    _assert_job_stats(notification.job_id, sent=1, count=1, delivered=1, failed=0)
    assert notification.updated_at == datetime(2000, 1, 2, 12, 0, 0)


def test_should_not_update_status_by_id_if_not_sending_and_does_not_update_job(notify_db, notify_db_session):
    notification = sample_notification(notify_db, notify_db_session, status='delivered')
    job = Job.query.get(notification.job_id)
    assert Notification.query.get(notification.id).status == 'delivered'
    assert not update_notification_status_by_id(notification.id, 'failed', 'failure')
    assert Notification.query.get(notification.id).status == 'delivered'
    assert job == Job.query.get(notification.job_id)


def test_should_update_status_if_created(notify_db, notify_db_session):
    notification = sample_notification(notify_db, notify_db_session, status='created')
    assert Notification.query.get(notification.id).status == 'created'
    assert update_notification_status_by_id(notification.id, 'failed', 'failure')


def test_should_by_able_to_update_status_by_id_from_pending_to_delivered(sample_template, sample_job):
    data = _notification_json(sample_template, job_id=sample_job.id, status='sending')
    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)
    assert Notification.query.get(notification.id).status == 'sending'
    assert update_notification_status_by_id(notification_id=notification.id, status='pending')
    assert Notification.query.get(notification.id).status == 'pending'
    _assert_notification_stats(notification.service_id, sms_requested=1, sms_delivered=0, sms_failed=0)
    _assert_job_stats(sample_job.id, sent=1, count=1, delivered=0, failed=0)

    assert update_notification_status_by_id(notification.id, 'delivered', 'delivered')
    assert Notification.query.get(notification.id).status == 'delivered'
    _assert_notification_stats(notification.service_id, sms_requested=1, sms_delivered=1, sms_failed=0)
    _assert_job_stats(notification.job_id, sent=1, count=1, delivered=1, failed=0)


def test_should_by_able_to_update_status_by_id_from_pending_to_temporary_failure(sample_template, sample_job):
    data = _notification_json(sample_template, job_id=sample_job.id, status='sending')
    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)
    assert Notification.query.get(notification.id).status == 'sending'
    assert update_notification_status_by_id(notification_id=notification.id, status='pending')
    assert Notification.query.get(notification.id).status == 'pending'
    _assert_notification_stats(notification.service_id, sms_requested=1, sms_delivered=0, sms_failed=0)
    _assert_job_stats(notification.job_id, sent=1, count=1, delivered=0, failed=0)

    assert update_notification_status_by_id(
        notification.id,
        status='permanent-failure',
        notification_statistics_status='failure')
    assert Notification.query.get(notification.id).status == 'temporary-failure'
    _assert_notification_stats(notification.service_id, sms_delivered=0, sms_requested=1, sms_failed=1)
    _assert_job_stats(sample_job.id, sent=1, count=1, delivered=0, failed=1)


def test_should_by_able_to_update_status_by_id_from_sending_to_permanent_failure(sample_template, sample_job):
    data = _notification_json(sample_template, job_id=sample_job.id, status='sending')
    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)
    assert Notification.query.get(notification.id).status == 'sending'

    assert update_notification_status_by_id(
        notification.id,
        status='permanent-failure',
        notification_statistics_status='failure'
    )
    assert Notification.query.get(notification.id).status == 'permanent-failure'
    _assert_notification_stats(notification.service_id, sms_requested=1, sms_delivered=0, sms_failed=1)
    _assert_job_stats(sample_job.id, sent=1, count=1, delivered=0, failed=1)


def test_should_not_update_status_one_notification_status_is_delivered(notify_db, notify_db_session,
                                                                       sample_email_template,
                                                                       ses_provider):
    notification = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                       template=sample_email_template,
                                       status='sending')
    assert Notification.query.get(notification.id).status == "sending"

    update_provider_stats(
        notification.id,
        'email',
        ses_provider.identifier)
    notification.reference = 'reference'
    dao_update_notification(notification)
    update_notification_status_by_reference('reference', 'delivered', 'delivered')
    assert Notification.query.get(notification.id).status == 'delivered'

    update_notification_status_by_reference('reference', 'failed', 'temporary-failure')
    assert Notification.query.get(notification.id).status == 'delivered'
    _assert_notification_stats(notification.service_id, emails_requested=1, emails_delivered=1, emails_failed=0)
    _assert_job_stats(notification.job_id, sent=1, count=1, delivered=1, failed=0)


def test_should_be_able_to_record_statistics_failure_for_sms(notify_db, notify_db_session, ):
    notification = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session, status='sending')
    assert Notification.query.get(notification.id).status == 'sending'

    assert update_notification_status_by_id(notification.id, 'permanent-failure', 'failure')
    assert Notification.query.get(notification.id).status == 'permanent-failure'
    _assert_notification_stats(notification.service_id, sms_requested=1, sms_delivered=0, sms_failed=1)
    _assert_job_stats(notification.job_id, sent=1, count=1, delivered=0, failed=1)


def test_should_be_able_to_record_statistics_failure_for_email(sample_email_template, sample_job, ses_provider):
    data = _notification_json(sample_email_template, job_id=sample_job.id, status='sending')
    notification = Notification(**data)
    dao_create_notification(notification, sample_email_template.template_type)

    update_provider_stats(
        notification.id,
        'email',
        ses_provider.identifier)
    notification.reference = 'reference'
    dao_update_notification(notification)
    count = update_notification_status_by_reference('reference', 'failed', 'failure')
    assert count == 1
    assert Notification.query.get(notification.id).status == 'failed'
    _assert_notification_stats(notification.service_id, emails_requested=1, emails_delivered=0, emails_failed=1)
    _assert_job_stats(notification.job_id, sent=1, count=1, delivered=0, failed=1)


def test_should_return_zero_count_if_no_notification_with_id():
    assert not update_notification_status_by_id(str(uuid.uuid4()), 'delivered', 'delivered')


def test_should_return_zero_count_if_no_notification_with_reference():
    assert not update_notification_status_by_reference('something', 'delivered', 'delivered')


def test_should_be_able_to_get_statistics_for_a_service(sample_template, mmg_provider):
    data = _notification_json(sample_template)

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    _assert_notification_stats(notification.service_id, sms_requested=1,
                               notification_created_at=notification.created_at.date())


def test_should_be_able_to_get_statistics_for_a_service_for_a_day(sample_template, mmg_provider):
    now = datetime.utcnow()
    data = _notification_json(sample_template)
    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)
    stat = dao_get_notification_statistics_for_service_and_day(
        sample_template.service.id, now.date()
    )
    assert stat.emails_requested == 0
    assert stat.emails_failed == 0
    assert stat.emails_delivered == 0
    assert stat.sms_requested == 1
    assert stat.sms_failed == 0
    assert stat.sms_delivered == 0
    assert stat.day == notification.created_at.date()
    assert stat.service_id == notification.service_id


def test_should_return_none_if_no_statistics_for_a_service_for_a_day(sample_template, mmg_provider):
    data = _notification_json(sample_template)

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)
    assert not dao_get_notification_statistics_for_service_and_day(
        sample_template.service.id, (datetime.utcnow() - timedelta(days=1)).date())


def test_should_be_able_to_get_all_statistics_for_a_service(sample_template, mmg_provider):
    data = _notification_json(sample_template)

    notification_1 = Notification(**data)
    notification_2 = Notification(**data)
    notification_3 = Notification(**data)
    dao_create_notification(notification_1, sample_template.template_type)
    dao_create_notification(notification_2, sample_template.template_type)
    dao_create_notification(notification_3, sample_template.template_type)

    _assert_notification_stats(sample_template.service.id, sms_requested=3)


def test_should_be_able_to_get_all_statistics_for_a_service_for_several_days(sample_template, mmg_provider):
    data = _notification_json(sample_template)

    today = datetime.utcnow()
    yesterday = datetime.utcnow() - timedelta(days=1)
    two_days_ago = datetime.utcnow() - timedelta(days=2)
    data.update({'created_at': today})
    notification_1 = Notification(**data)
    data.update({'created_at': yesterday})
    notification_2 = Notification(**data)
    data.update({'created_at': two_days_ago})
    notification_3 = Notification(**data)

    dao_create_notification(notification_1, sample_template.template_type)
    dao_create_notification(notification_2, sample_template.template_type)
    dao_create_notification(notification_3, sample_template.template_type)

    stats = dao_get_notification_statistics_for_service(sample_template.service.id)
    assert len(stats) == 3
    assert stats[0].emails_requested == 0
    assert stats[0].sms_requested == 1
    assert stats[0].day == today.date()
    assert stats[1].emails_requested == 0
    assert stats[1].sms_requested == 1
    assert stats[1].day == yesterday.date()
    assert stats[2].emails_requested == 0
    assert stats[2].sms_requested == 1
    assert stats[2].day == two_days_ago.date()


def test_should_be_empty_list_if_no_statistics_for_a_service(sample_service):
    assert len(dao_get_notification_statistics_for_service(sample_service.id)) == 0


def test_should_be_able_to_get_all_statistics_for_a_service_for_several_days_previous(sample_template,
                                                                                      mmg_provider):
    data = _notification_json(sample_template)

    today = datetime.utcnow()
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    eight_days_ago = datetime.utcnow() - timedelta(days=8)
    data.update({'created_at': today})
    notification_1 = Notification(**data)
    data.update({'created_at': seven_days_ago})
    notification_2 = Notification(**data)
    data.update({'created_at': eight_days_ago})
    notification_3 = Notification(**data)
    dao_create_notification(notification_1, sample_template.template_type)
    dao_create_notification(notification_2, sample_template.template_type)
    dao_create_notification(notification_3, sample_template.template_type)

    stats = dao_get_notification_statistics_for_service(sample_template.service.id, 7)
    assert len(stats) == 2
    assert stats[0].emails_requested == 0
    assert stats[0].sms_requested == 1
    assert stats[0].day == today.date()
    assert stats[1].emails_requested == 0
    assert stats[1].sms_requested == 1
    assert stats[1].day == seven_days_ago.date()


def test_create_notification_creates_notification_with_personalisation(notify_db, notify_db_session,
                                                                       sample_template_with_placeholders,
                                                                       sample_job, mmg_provider):
    assert Notification.query.count() == 0
    assert NotificationStatistics.query.count() == 0
    assert TemplateStatistics.query.count() == 0

    data = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                               template=sample_template_with_placeholders,
                               job=sample_job,
                               personalisation={'name': 'Jo'},
                               status='created')

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data.to == notification_from_db.to
    assert data.job_id == notification_from_db.job_id
    assert data.service == notification_from_db.service
    assert data.template == notification_from_db.template
    assert data.template_version == notification_from_db.template_version
    assert data.created_at == notification_from_db.created_at
    assert 'created' == notification_from_db.status
    assert {'name': 'Jo'} == notification_from_db.personalisation
    _assert_job_stats(sample_job.id, sent=1, count=1, delivered=0, failed=0)

    stats = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_template_with_placeholders.service.id).first()
    assert stats.emails_requested == 0
    assert stats.sms_requested == 1

    template_stats = TemplateStatistics.query.filter(
        TemplateStatistics.service_id == sample_template_with_placeholders.service.id,
        TemplateStatistics.template_id == sample_template_with_placeholders.id).first()
    assert template_stats.service_id == sample_template_with_placeholders.service.id
    assert template_stats.template_id == sample_template_with_placeholders.id
    assert template_stats.usage_count == 1


def test_save_notification_creates_sms_and_template_stats(sample_template, sample_job, mmg_provider):
    assert Notification.query.count() == 0
    assert NotificationStatistics.query.count() == 0
    assert TemplateStatistics.query.count() == 0

    data = _notification_json(sample_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['job_id'] == notification_from_db.job_id
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['template_version'] == notification_from_db.template_version
    assert data['created_at'] == notification_from_db.created_at
    assert 'created' == notification_from_db.status
    _assert_job_stats(sample_job.id, sent=1, count=1, delivered=0, failed=0)

    stats = NotificationStatistics.query.filter(NotificationStatistics.service_id == sample_template.service.id).first()
    assert stats.emails_requested == 0
    assert stats.sms_requested == 1

    template_stats = TemplateStatistics.query.filter(TemplateStatistics.service_id == sample_template.service.id,
                                                     TemplateStatistics.template_id == sample_template.id).first()
    assert template_stats.service_id == sample_template.service.id
    assert template_stats.template_id == sample_template.id
    assert template_stats.usage_count == 1


def test_save_notification_and_create_email_and_template_stats(sample_email_template, sample_job, ses_provider):
    assert Notification.query.count() == 0
    assert NotificationStatistics.query.count() == 0
    assert TemplateStatistics.query.count() == 0

    data = _notification_json(sample_email_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification, sample_email_template.template_type)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['job_id'] == notification_from_db.job_id
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['template_version'] == notification_from_db.template_version
    assert data['created_at'] == notification_from_db.created_at
    assert 'created' == notification_from_db.status
    _assert_job_stats(sample_job.id, sent=1, count=1, delivered=0, failed=0)

    stats = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_email_template.service.id).first()

    assert stats.emails_requested == 1
    assert stats.sms_requested == 0

    template_stats = TemplateStatistics.query.filter(TemplateStatistics.service_id == sample_email_template.service.id,
                                                     TemplateStatistics.template_id == sample_email_template.id).first()  # noqa

    assert template_stats.service_id == sample_email_template.service.id
    assert template_stats.template_id == sample_email_template.id
    assert template_stats.usage_count == 1


@freeze_time("2016-01-01 00:00:00.000000")
def test_save_notification_handles_midnight_properly(sample_template, sample_job, mmg_provider):
    assert Notification.query.count() == 0
    data = _notification_json(sample_template, sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    assert Notification.query.count() == 1

    stats = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_template.service.id).first()

    assert stats.day == date(2016, 1, 1)


@freeze_time("2016-01-01 23:59:59.999999")
def test_save_notification_handles_just_before_midnight_properly(sample_template, sample_job, mmg_provider):
    assert Notification.query.count() == 0
    data = _notification_json(sample_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    assert Notification.query.count() == 1

    stats = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_template.service.id).first()

    assert stats.day == date(2016, 1, 1)


def test_save_notification_and_increment_email_stats(sample_email_template, sample_job, ses_provider):
    assert Notification.query.count() == 0
    data = _notification_json(sample_email_template, job_id=sample_job.id)

    notification_1 = Notification(**data)
    notification_2 = Notification(**data)
    dao_create_notification(notification_1, sample_email_template.template_type)

    assert Notification.query.count() == 1

    stats1 = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_email_template.service.id).first()

    assert stats1.emails_requested == 1
    assert stats1.sms_requested == 0

    dao_create_notification(notification_2, sample_email_template.template_type)

    assert Notification.query.count() == 2

    stats2 = NotificationStatistics.query.filter(
        NotificationStatistics.service_id == sample_email_template.service.id).first()

    assert stats2.emails_requested == 2
    assert stats2.sms_requested == 0


def test_save_notification_and_increment_sms_stats(sample_template, sample_job, mmg_provider):
    assert Notification.query.count() == 0
    data = _notification_json(sample_template, sample_job.id)

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


def test_not_save_notification_and_not_create_stats_on_commit_error(sample_template, sample_job, mmg_provider):
    random_id = str(uuid.uuid4())

    assert Notification.query.count() == 0
    data = _notification_json(sample_template, job_id=random_id)

    notification = Notification(**data)
    with pytest.raises(SQLAlchemyError):
        dao_create_notification(notification, sample_template.template_type)

    assert Notification.query.count() == 0
    assert Job.query.get(sample_job.id).notifications_sent == 0
    assert NotificationStatistics.query.count() == 0
    assert TemplateStatistics.query.count() == 0


def test_save_notification_and_increment_job(sample_template, sample_job, mmg_provider):
    assert Notification.query.count() == 0
    data = _notification_json(sample_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['job_id'] == notification_from_db.job_id
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['template_version'] == notification_from_db.template_version
    assert data['created_at'] == notification_from_db.created_at
    assert 'created' == notification_from_db.status
    assert Job.query.get(sample_job.id).notifications_sent == 1

    notification_2 = Notification(**data)
    dao_create_notification(notification_2, sample_template.template_type)
    assert Notification.query.count() == 2
    # count is off because the count is defaulted to 1 in the sample_job
    _assert_job_stats(sample_job.id, sent=2, count=1)


def test_should_not_increment_job_if_notification_fails_to_persist(sample_template, sample_job, mmg_provider):
    random_id = str(uuid.uuid4())
    assert Notification.query.count() == 0
    data = _notification_json(sample_template, job_id=sample_job.id, id=random_id)

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


def test_save_notification_and_increment_correct_job(notify_db, notify_db_session, sample_template, mmg_provider):
    from tests.app.conftest import sample_job
    job_1 = sample_job(notify_db, notify_db_session, sample_template.service)
    job_2 = sample_job(notify_db, notify_db_session, sample_template.service)

    assert Notification.query.count() == 0
    data = _notification_json(sample_template, job_id=job_1.id)

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['job_id'] == notification_from_db.job_id
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['template_version'] == notification_from_db.template_version
    assert data['created_at'] == notification_from_db.created_at
    assert 'created' == notification_from_db.status
    assert job_1.id != job_2.id
    _assert_job_stats(job_id=job_1.id, sent=1, count=1)
    _assert_job_stats(job_id=job_2.id, sent=0, count=1)


def test_save_notification_with_no_job(sample_template, mmg_provider):
    assert Notification.query.count() == 0
    data = _notification_json(sample_template)

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['template_version'] == notification_from_db.template_version
    assert data['created_at'] == notification_from_db.created_at
    assert 'created' == notification_from_db.status


def test_get_notification(sample_notification):
    notification_from_db = get_notification(
        sample_notification.service.id,
        sample_notification.id)
    assert sample_notification == notification_from_db


def test_save_notification_no_job_id(sample_template, mmg_provider):
    assert Notification.query.count() == 0
    data = _notification_json(sample_template)

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['template_version'] == notification_from_db.template_version
    assert 'created' == notification_from_db.status
    assert data.get('job_id') is None


def test_get_notification_for_job(sample_notification):
    notification_from_db = get_notification_for_job(
        sample_notification.service.id,
        sample_notification.job_id,
        sample_notification.id)
    assert sample_notification == notification_from_db


def test_get_all_notifications_for_job(notify_db, notify_db_session, sample_job):
    for i in range(0, 5):
        try:
            sample_notification(notify_db,
                                notify_db_session,
                                service=sample_job.service,
                                template=sample_job.template,
                                job=sample_job)
        except IntegrityError:
            pass

    notifications_from_db = get_notifications_for_job(sample_job.service.id, sample_job.id).items
    assert len(notifications_from_db) == 5
    _assert_notification_stats(sample_job.service.id, sms_requested=5)


def test_get_all_notifications_for_job_by_status(notify_db, notify_db_session, sample_job):
    notifications = partial(get_notifications_for_job, sample_job.service.id, sample_job.id)

    for status in NOTIFICATION_STATUS_TYPES:
        sample_notification(
            notify_db,
            notify_db_session,
            service=sample_job.service,
            template=sample_job.template,
            job=sample_job,
            status=status
        )

    assert len(notifications().items) == len(NOTIFICATION_STATUS_TYPES)

    for status in NOTIFICATION_STATUS_TYPES:
        assert len(notifications(filter_dict={'status': status}).items) == 1

    assert len(notifications(filter_dict={'status': NOTIFICATION_STATUS_TYPES[:3]}).items) == 3


def test_update_notification(sample_notification, sample_template):
    assert sample_notification.status == 'created'
    sample_notification.status = 'failed'
    dao_update_notification(sample_notification)
    notification_from_db = Notification.query.get(sample_notification.id)
    assert notification_from_db.status == 'failed'


@freeze_time("2016-01-10 12:00:00.000000")
def test_should_delete_notifications_after_seven_days(notify_db, notify_db_session):
    assert len(Notification.query.all()) == 0

    # create one notification a day between 1st and 10th from 11:00 to 19:00
    for i in range(1, 11):
        past_date = '2016-01-{0:02d}  {0:02d}:00:00.000000'.format(i)
        with freeze_time(past_date):
            sample_notification(notify_db, notify_db_session, created_at=datetime.utcnow(), status="failed")

    all_notifications = Notification.query.all()
    assert len(all_notifications) == 10

    # Records from before 3rd should be deleted
    delete_notifications_created_more_than_a_week_ago('failed')
    remaining_notifications = Notification.query.all()
    assert len(remaining_notifications) == 8
    for notification in remaining_notifications:
        assert notification.created_at.date() >= date(2016, 1, 3)


@freeze_time("2016-01-10 12:00:00.000000")
def test_should_not_delete_notification_history(notify_db, notify_db_session):
    with freeze_time('2016-01-01 12:00'):
        notification = sample_notification(notify_db, notify_db_session, created_at=datetime.utcnow(), status="failed")
        notification_id = notification.id

    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 1

    delete_notifications_created_more_than_a_week_ago('failed')

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 1
    assert NotificationHistory.query.one().id == notification_id


def test_should_not_delete_failed_notifications_before_seven_days(notify_db, notify_db_session):
    should_delete = datetime.utcnow() - timedelta(days=8)
    do_not_delete = datetime.utcnow() - timedelta(days=7)
    sample_notification(notify_db, notify_db_session, created_at=should_delete, status="failed",
                        to_field="should_delete")
    sample_notification(notify_db, notify_db_session, created_at=do_not_delete, status="failed",
                        to_field="do_not_delete")
    assert len(Notification.query.all()) == 2
    delete_notifications_created_more_than_a_week_ago('failed')
    assert len(Notification.query.all()) == 1
    assert Notification.query.first().to == 'do_not_delete'


@freeze_time("2016-03-30")
def test_save_new_notification_creates_template_stats(sample_template, sample_job, mmg_provider):
    assert Notification.query.count() == 0
    assert TemplateStatistics.query.count() == 0
    data = _notification_json(sample_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    assert TemplateStatistics.query.count() == 1
    template_stats = TemplateStatistics.query.filter(TemplateStatistics.service_id == sample_template.service.id,
                                                     TemplateStatistics.template_id == sample_template.id).first()
    assert template_stats.service_id == sample_template.service.id
    assert template_stats.template_id == sample_template.id
    assert template_stats.usage_count == 1
    assert template_stats.day == date(2016, 3, 30)


@freeze_time("2016-03-30")
def test_save_new_notification_creates_template_stats_per_day(sample_template, sample_job, mmg_provider):
    assert Notification.query.count() == 0
    assert TemplateStatistics.query.count() == 0
    data = _notification_json(sample_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    assert TemplateStatistics.query.count() == 1
    template_stats = TemplateStatistics.query.filter(TemplateStatistics.service_id == sample_template.service.id,
                                                     TemplateStatistics.template_id == sample_template.id).first()
    assert template_stats.service_id == sample_template.service.id
    assert template_stats.template_id == sample_template.id
    assert template_stats.usage_count == 1
    assert template_stats.day == date(2016, 3, 30)

    # move on one day
    with freeze_time('2016-03-31'):
        assert TemplateStatistics.query.count() == 1
        new_notification = Notification(**data)
        dao_create_notification(new_notification, sample_template.template_type)

    assert TemplateStatistics.query.count() == 2
    first_stats = TemplateStatistics.query.filter(TemplateStatistics.day == datetime(2016, 3, 30)).first()
    second_stats = TemplateStatistics.query.filter(TemplateStatistics.day == datetime(2016, 3, 31)).first()

    assert first_stats.template_id == second_stats.template_id
    assert first_stats.service_id == second_stats.service_id

    assert first_stats.day == date(2016, 3, 30)
    assert first_stats.usage_count == 1

    assert second_stats.day == date(2016, 3, 31)
    assert second_stats.usage_count == 1


def test_save_another_notification_increments_template_stats(sample_template, sample_job, mmg_provider):
    assert Notification.query.count() == 0
    assert TemplateStatistics.query.count() == 0
    data = _notification_json(sample_template, job_id=sample_job.id)

    notification_1 = Notification(**data)
    notification_2 = Notification(**data)
    dao_create_notification(notification_1, sample_template.template_type)

    assert TemplateStatistics.query.count() == 1
    template_stats = TemplateStatistics.query.filter(TemplateStatistics.service_id == sample_template.service.id,
                                                     TemplateStatistics.template_id == sample_template.id).first()
    assert template_stats.service_id == sample_template.service.id
    assert template_stats.template_id == sample_template.id
    assert template_stats.usage_count == 1

    dao_create_notification(notification_2, sample_template.template_type)

    assert TemplateStatistics.query.count() == 1
    template_stats = TemplateStatistics.query.filter(TemplateStatistics.service_id == sample_template.service.id,
                                                     TemplateStatistics.template_id == sample_template.id).first()
    assert template_stats.usage_count == 2


def test_successful_notification_inserts_followed_by_failure_does_not_increment_template_stats(sample_template,
                                                                                               sample_job,
                                                                                               mmg_provider):
    assert Notification.query.count() == 0
    assert NotificationStatistics.query.count() == 0
    assert TemplateStatistics.query.count() == 0

    data = _notification_json(sample_template, job_id=sample_job.id)

    notification_1 = Notification(**data)
    notification_2 = Notification(**data)
    notification_3 = Notification(**data)
    dao_create_notification(notification_1, sample_template.template_type)
    dao_create_notification(notification_2, sample_template.template_type)
    dao_create_notification(notification_3, sample_template.template_type)

    _assert_notification_stats(sample_template.service.id, sms_requested=3)

    assert TemplateStatistics.query.count() == 1
    template_stats = TemplateStatistics.query.filter(TemplateStatistics.service_id == sample_template.service.id,
                                                     TemplateStatistics.template_id == sample_template.id).first()
    assert template_stats.service_id == sample_template.service.id
    assert template_stats.template_id == sample_template.id
    assert template_stats.usage_count == 3

    failing_notification = Notification(**data)
    try:
        # Mess up db in really bad way
        db.session.execute('DROP TABLE TEMPLATE_STATISTICS')
        dao_create_notification(failing_notification, sample_template.template_type)
    except Exception as e:
        # There should be no additional notification stats or counts
        _assert_notification_stats(sample_template.service.id, sms_requested=3)


@freeze_time("2016-03-30")
def test_get_template_stats_for_service_returns_stats_in_reverse_date_order(sample_template, sample_job):
    template_stats = dao_get_template_statistics_for_service(sample_template.service.id)
    assert len(template_stats) == 0
    data = _notification_json(sample_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification, sample_template.template_type)

    # move on one day
    with freeze_time('2016-03-31'):
        new_notification = Notification(**data)
        dao_create_notification(new_notification, sample_template.template_type)

    # move on one more day
    with freeze_time('2016-04-01'):
        new_notification = Notification(**data)
        dao_create_notification(new_notification, sample_template.template_type)

    template_stats = dao_get_template_statistics_for_service(sample_template.service_id)
    assert len(template_stats) == 3
    assert template_stats[0].day == date(2016, 4, 1)
    assert template_stats[1].day == date(2016, 3, 31)
    assert template_stats[2].day == date(2016, 3, 30)


@freeze_time('2016-04-09')
def test_get_template_stats_for_service_returns_stats_can_limit_number_of_days_returned(sample_template):
    template_stats = dao_get_template_statistics_for_service(sample_template.service.id)
    assert len(template_stats) == 0

    # Make 9 stats records from 1st to 9th April
    for i in range(1, 10):
        past_date = '2016-04-0{}'.format(i)
        with freeze_time(past_date):
            template_stats = TemplateStatistics(template_id=sample_template.id,
                                                service_id=sample_template.service_id)
            db.session.add(template_stats)
            db.session.commit()

    # Retrieve last week of stats
    template_stats = dao_get_template_statistics_for_service(sample_template.service_id, limit_days=7)
    assert len(template_stats) == 8
    assert template_stats[0].day == date(2016, 4, 9)
    # Final day of stats should be the same as today, eg Monday
    assert template_stats[0].day.isoweekday() == template_stats[7].day.isoweekday()
    assert template_stats[7].day == date(2016, 4, 2)


@freeze_time('2016-04-09')
def test_get_template_stats_for_service_returns_stats_returns_all_stats_if_no_limit(sample_template):
    template_stats = dao_get_template_statistics_for_service(sample_template.service.id)
    assert len(template_stats) == 0

    # make 9 stats records from 1st to 9th April
    for i in range(1, 10):
        past_date = '2016-04-0{}'.format(i)
        with freeze_time(past_date):
            template_stats = TemplateStatistics(template_id=sample_template.id,
                                                service_id=sample_template.service_id)
            db.session.add(template_stats)
            db.session.commit()

    template_stats = dao_get_template_statistics_for_service(sample_template.service_id)
    assert len(template_stats) == 9
    assert template_stats[0].day == date(2016, 4, 9)
    assert template_stats[8].day == date(2016, 4, 1)


@freeze_time('2016-04-30')
def test_get_template_stats_for_service_returns_no_result_if_no_usage_within_limit_days(sample_template):
    template_stats = dao_get_template_statistics_for_service(sample_template.service.id)
    assert len(template_stats) == 0

    # make 9 stats records from 1st to 9th April - no data after 10th
    for i in range(1, 10):
        past_date = '2016-04-0{}'.format(i)
        with freeze_time(past_date):
            template_stats = TemplateStatistics(template_id=sample_template.id,
                                                service_id=sample_template.service_id)
            db.session.add(template_stats)
            db.session.commit()

    # Retrieve a week of stats - read date is 2016-04-30
    template_stats = dao_get_template_statistics_for_service(sample_template.service_id, limit_days=7)
    assert len(template_stats) == 0

    # Retrieve a month of stats - read date is 2016-04-30
    template_stats = dao_get_template_statistics_for_service(sample_template.service_id, limit_days=30)
    assert len(template_stats) == 9


def test_get_template_stats_for_service_with_limit_if_no_records_returns_empty_list(sample_template):
    template_stats = dao_get_template_statistics_for_service(sample_template.service.id, limit_days=7)
    assert len(template_stats) == 0


@freeze_time("2016-01-10")
def test_should_limit_notifications_return_by_day_limit_plus_one(notify_db, notify_db_session, sample_service):
    assert len(Notification.query.all()) == 0

    # create one notification a day between 1st and 9th
    for i in range(1, 11):
        past_date = '2016-01-{0:02d}'.format(i)
        with freeze_time(past_date):
            sample_notification(notify_db, notify_db_session, created_at=datetime.utcnow(), status="failed")

    all_notifications = Notification.query.all()
    assert len(all_notifications) == 10

    all_notifications = get_notifications_for_service(sample_service.id, limit_days=10).items
    assert len(all_notifications) == 10

    all_notifications = get_notifications_for_service(sample_service.id, limit_days=1).items
    assert len(all_notifications) == 2


@pytest.mark.parametrize(
    "char_count, expected_sms_fragment_count",
    [
        (159, 1),
        (160, 1),
        (161, 2),
        (306, 2),
        (307, 3),
        (459, 3),
        (460, 4),
        (461, 4)
    ])
def test_sms_fragment_count(char_count, expected_sms_fragment_count):
    assert get_sms_fragment_count(char_count) == expected_sms_fragment_count


def test_creating_notification_adds_to_notification_history(sample_template):
    data = _notification_json(sample_template)
    notification = Notification(**data)

    dao_create_notification(notification, sample_template.template_type)

    assert Notification.query.count() == 1

    hist = NotificationHistory.query.one()
    assert hist.id == notification.id
    assert hist.created_at == notification.created_at
    assert hist.status == notification.status
    assert not hasattr(hist, 'to')
    assert not hasattr(hist, '_personalisation')


def test_updating_notification_updates_notification_history(sample_notification):
    hist = NotificationHistory.query.one()
    assert hist.id == sample_notification.id
    assert hist.status == 'created'

    sample_notification.status = 'sending'
    dao_update_notification(sample_notification)

    hist = NotificationHistory.query.one()
    assert hist.id == sample_notification.id
    assert hist.status == 'sending'


def _notification_json(sample_template, job_id=None, id=None, status=None):
    data = {
        'to': '+44709123456',
        'service': sample_template.service,
        'service_id': sample_template.service.id,
        'template': sample_template,
        'template_id': sample_template.id,
        'template_version': sample_template.version,
        'created_at': datetime.utcnow(),
        'billable_units': 1,
        'notification_type': sample_template.template_type,
        'key_type': KEY_TYPE_NORMAL
    }
    if job_id:
        data.update({'job_id': job_id})
    if id:
        data.update({'id': id})
    if status:
        data.update({'status': status})
    return data


def _assert_notification_stats(service_id,
                               emails_delivered=0, emails_requested=0, emails_failed=0,
                               sms_delivered=0, sms_requested=0, sms_failed=0,
                               notification_created_at=None):
    stats = NotificationStatistics.query.filter_by(service_id=service_id).all()
    assert len(stats) == 1
    assert stats[0].emails_delivered == emails_delivered
    assert stats[0].emails_requested == emails_requested
    assert stats[0].emails_failed == emails_failed
    assert stats[0].sms_delivered == sms_delivered
    assert stats[0].sms_requested == sms_requested
    assert stats[0].sms_failed == sms_failed
    assert stats[0].day == notification_created_at if notification_created_at else True


def _assert_job_stats(job_id, sent=0, count=0, delivered=0, failed=0):
    job = Job.query.get(job_id)
    assert job.notifications_sent == sent
    assert job.notification_count == count
    assert job.notifications_delivered == delivered
    assert job.notifications_failed == failed
