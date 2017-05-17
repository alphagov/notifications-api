from datetime import datetime, timedelta, date
import uuid
from functools import partial

import pytest
from freezegun import freeze_time
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.models import (
    Notification,
    NotificationHistory,
    Job,
    NotificationStatistics,
    TemplateStatistics,
    ScheduledNotification,
    NOTIFICATION_STATUS_TYPES,
    NOTIFICATION_STATUS_TYPES_FAILED,
    NOTIFICATION_SENT,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST)

from app.dao.notifications_dao import (
    dao_create_notification,
    dao_get_last_template_usage,
    dao_get_notification_statistics_for_service_and_day,
    dao_get_potential_notification_statistics_for_day,
    dao_get_template_usage,
    dao_update_notification,
    delete_notifications_created_more_than_a_week_ago,
    get_notification_by_id,
    get_notification_for_job,
    get_notification_billable_unit_count_per_month,
    get_notification_with_personalisation,
    get_notifications_for_job,
    get_notifications_for_service,
    get_total_sent_notifications_in_date_range,
    update_notification_status_by_id,
    update_notification_status_by_reference,
    dao_delete_notifications_and_history_by_id,
    dao_timeout_notifications,
    is_delivery_slow_for_provider,
    dao_update_notifications_sent_to_dvla,
    dao_get_notifications_by_to_field,
    dao_created_scheduled_notification, dao_get_scheduled_notifications)

from app.dao.services_dao import dao_update_service
from tests.app.db import create_notification
from tests.app.conftest import (
    sample_notification,
    sample_template,
    sample_email_template,
    sample_service,
    sample_job,
    sample_notification_history as create_notification_history
)


def test_should_have_decorated_notifications_dao_functions():
    assert dao_get_last_template_usage.__wrapped__.__name__ == 'dao_get_last_template_usage'  # noqa
    assert dao_get_template_usage.__wrapped__.__name__ == 'dao_get_template_usage'  # noqa
    assert dao_get_potential_notification_statistics_for_day.__wrapped__.__name__ == 'dao_get_potential_notification_statistics_for_day'  # noqa
    assert dao_create_notification.__wrapped__.__name__ == 'dao_create_notification'  # noqa
    assert update_notification_status_by_id.__wrapped__.__name__ == 'update_notification_status_by_id'  # noqa
    assert dao_update_notification.__wrapped__.__name__ == 'dao_update_notification'  # noqa
    assert update_notification_status_by_reference.__wrapped__.__name__ == 'update_notification_status_by_reference'  # noqa
    assert get_notification_for_job.__wrapped__.__name__ == 'get_notification_for_job'  # noqa
    assert get_notifications_for_job.__wrapped__.__name__ == 'get_notifications_for_job'  # noqa
    assert get_notification_with_personalisation.__wrapped__.__name__ == 'get_notification_with_personalisation'  # noqa
    assert get_notifications_for_service.__wrapped__.__name__ == 'get_notifications_for_service'  # noqa
    assert get_notification_by_id.__wrapped__.__name__ == 'get_notification_by_id'  # noqa
    assert delete_notifications_created_more_than_a_week_ago.__wrapped__.__name__ == 'delete_notifications_created_more_than_a_week_ago'  # noqa
    assert dao_delete_notifications_and_history_by_id.__wrapped__.__name__ == 'dao_delete_notifications_and_history_by_id'  # noqa


def test_should_be_able_to_get_template_usage_history(notify_db, notify_db_session, sample_service):
    with freeze_time('2000-01-01 12:00:00'):
        sms = sample_template(notify_db, notify_db_session)
        notification = sample_notification(notify_db, notify_db_session, service=sample_service, template=sms)
        results = dao_get_last_template_usage(sms.id)
        assert results.template.name == 'Template Name'
        assert results.template.template_type == 'sms'
        assert results.created_at == datetime(year=2000, month=1, day=1, hour=12, minute=0, second=0)
        assert results.template_id == sms.id
        assert results.id == notification.id


def test_should_be_able_to_get_all_template_usage_history_order_by_notification_created_at(
        notify_db,
        notify_db_session,
        sample_service):
    sms = sample_template(notify_db, notify_db_session)

    sample_notification(notify_db, notify_db_session, service=sample_service, template=sms)
    sample_notification(notify_db, notify_db_session, service=sample_service, template=sms)
    sample_notification(notify_db, notify_db_session, service=sample_service, template=sms)
    most_recent = sample_notification(notify_db, notify_db_session, service=sample_service, template=sms)

    results = dao_get_last_template_usage(sms.id)
    assert results.id == most_recent.id


def test_template_usage_should_ignore_test_keys(
        notify_db,
        notify_db_session,
        sample_team_api_key,
        sample_test_api_key
):
    sms = sample_template(notify_db, notify_db_session)

    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
    two_minutes_ago = datetime.utcnow() - timedelta(minutes=2)

    team_key = sample_notification(
        notify_db,
        notify_db_session,
        created_at=two_minutes_ago,
        template=sms,
        api_key_id=sample_team_api_key.id,
        key_type=KEY_TYPE_TEAM)
    sample_notification(
        notify_db,
        notify_db_session,
        created_at=one_minute_ago,
        template=sms,
        api_key_id=sample_test_api_key.id,
        key_type=KEY_TYPE_TEST)

    results = dao_get_last_template_usage(sms.id)
    assert results.id == team_key.id


def test_should_be_able_to_get_no_template_usage_history_if_no_notifications_using_template(
        notify_db,
        notify_db_session):
    sms = sample_template(notify_db, notify_db_session)

    results = dao_get_last_template_usage(sms.id)
    assert not results


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


def test_template_history_should_ignore_test_keys(
    notify_db,
    notify_db_session,
    sample_team_api_key,
    sample_test_api_key,
    sample_api_key
):
    sms = sample_template(notify_db, notify_db_session)

    sample_notification(
        notify_db, notify_db_session, template=sms, api_key_id=sample_api_key.id, key_type=KEY_TYPE_NORMAL)
    sample_notification(
        notify_db, notify_db_session, template=sms, api_key_id=sample_team_api_key.id, key_type=KEY_TYPE_TEAM)
    sample_notification(
        notify_db, notify_db_session, template=sms, api_key_id=sample_test_api_key.id, key_type=KEY_TYPE_TEST)
    sample_notification(
        notify_db, notify_db_session, template=sms)

    results = dao_get_template_usage(sms.service_id)
    assert results[0].name == 'Template Name'
    assert results[0].template_type == 'sms'
    assert results[0].count == 3


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
    dao_create_notification(notification)

    assert Notification.query.get(notification.id).status == "sending"
    notification.reference = 'reference'
    dao_update_notification(notification)

    updated = update_notification_status_by_reference('reference', 'delivered')
    assert updated.status == 'delivered'
    assert Notification.query.get(notification.id).status == 'delivered'


def test_should_by_able_to_update_status_by_id(sample_template, sample_job, mmg_provider):
    with freeze_time('2000-01-01 12:00:00'):
        data = _notification_json(sample_template, job_id=sample_job.id, status='sending')
        notification = Notification(**data)
        dao_create_notification(notification)
        assert notification._status_enum == 'sending'
        assert notification._status_fkey == 'sending'

    assert Notification.query.get(notification.id).status == 'sending'

    with freeze_time('2000-01-02 12:00:00'):
        updated = update_notification_status_by_id(notification.id, 'delivered')

    assert updated.status == 'delivered'
    assert updated.updated_at == datetime(2000, 1, 2, 12, 0, 0)
    assert Notification.query.get(notification.id).status == 'delivered'
    assert notification.updated_at == datetime(2000, 1, 2, 12, 0, 0)
    assert notification._status_enum == 'delivered'
    assert notification._status_fkey == 'delivered'


def test_should_not_update_status_by_id_if_not_sending_and_does_not_update_job(notify_db, notify_db_session):
    job = sample_job(notify_db, notify_db_session)
    notification = sample_notification(notify_db, notify_db_session, status='delivered', job=job)
    assert Notification.query.get(notification.id).status == 'delivered'
    assert not update_notification_status_by_id(notification.id, 'failed')
    assert Notification.query.get(notification.id).status == 'delivered'
    assert job == Job.query.get(notification.job_id)


def test_should_not_update_status_by_reference_if_not_sending_and_does_not_update_job(notify_db, notify_db_session):
    job = sample_job(notify_db, notify_db_session)
    notification = sample_notification(notify_db, notify_db_session, status='delivered', reference='reference', job=job)
    assert Notification.query.get(notification.id).status == 'delivered'
    assert not update_notification_status_by_reference('reference', 'failed')
    assert Notification.query.get(notification.id).status == 'delivered'
    assert job == Job.query.get(notification.job_id)


def test_should_update_status_by_id_if_created(notify_db, notify_db_session):
    notification = sample_notification(notify_db, notify_db_session, status='created')
    assert Notification.query.get(notification.id).status == 'created'
    updated = update_notification_status_by_id(notification.id, 'failed')
    assert Notification.query.get(notification.id).status == 'failed'
    assert updated.status == 'failed'


def test_should_not_update_status_by_reference_if_in_sent_status(notify_db, notify_db_session):
    notification = sample_notification(
        notify_db,
        notify_db_session,
        status=NOTIFICATION_SENT,
        reference='foo'
    )

    update_notification_status_by_reference('foo', 'failed')
    assert Notification.query.get(notification.id).status == NOTIFICATION_SENT


def test_should_not_update_status_by_id_if_in_sent_status(notify_db, notify_db_session):
    notification = sample_notification(
        notify_db,
        notify_db_session,
        status=NOTIFICATION_SENT
    )

    update_notification_status_by_id(notification.id, 'failed')

    assert Notification.query.get(notification.id).status == NOTIFICATION_SENT


def test_should_not_update_status_by_reference_if_not_sending(notify_db, notify_db_session):
    notification = sample_notification(notify_db, notify_db_session, status='created', reference='reference')
    assert Notification.query.get(notification.id).status == 'created'
    updated = update_notification_status_by_reference('reference', 'failed')
    assert Notification.query.get(notification.id).status == 'created'
    assert not updated


def test_should_by_able_to_update_status_by_id_from_pending_to_delivered(sample_template, sample_job):
    data = _notification_json(sample_template, job_id=sample_job.id, status='sending')
    notification = Notification(**data)
    dao_create_notification(notification)
    assert Notification.query.get(notification.id).status == 'sending'
    assert update_notification_status_by_id(notification_id=notification.id, status='pending')
    assert Notification.query.get(notification.id).status == 'pending'

    assert update_notification_status_by_id(notification.id, 'delivered')
    assert Notification.query.get(notification.id).status == 'delivered'


def test_should_by_able_to_update_status_by_id_from_pending_to_temporary_failure(sample_template, sample_job):
    data = _notification_json(sample_template, job_id=sample_job.id, status='sending')
    notification = Notification(**data)
    dao_create_notification(notification)
    assert Notification.query.get(notification.id).status == 'sending'
    assert update_notification_status_by_id(notification_id=notification.id, status='pending')
    assert Notification.query.get(notification.id).status == 'pending'

    assert update_notification_status_by_id(
        notification.id,
        status='permanent-failure')
    assert Notification.query.get(notification.id).status == 'temporary-failure'


def test_should_by_able_to_update_status_by_id_from_sending_to_permanent_failure(sample_template, sample_job):
    data = _notification_json(sample_template, job_id=sample_job.id, status='sending')
    notification = Notification(**data)
    dao_create_notification(notification)
    assert Notification.query.get(notification.id).status == 'sending'

    assert update_notification_status_by_id(
        notification.id,
        status='permanent-failure'
    )
    assert Notification.query.get(notification.id).status == 'permanent-failure'


def test_should_not_update_status_one_notification_status_is_delivered(notify_db, notify_db_session,
                                                                       sample_email_template,
                                                                       ses_provider):
    notification = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                       template=sample_email_template,
                                       status='sending')
    assert Notification.query.get(notification.id).status == "sending"

    notification.reference = 'reference'
    dao_update_notification(notification)
    update_notification_status_by_reference('reference', 'delivered')
    assert Notification.query.get(notification.id).status == 'delivered'

    update_notification_status_by_reference('reference', 'failed')
    assert Notification.query.get(notification.id).status == 'delivered'


def test_should_return_zero_count_if_no_notification_with_id():
    assert not update_notification_status_by_id(str(uuid.uuid4()), 'delivered')


def test_should_return_zero_count_if_no_notification_with_reference():
    assert not update_notification_status_by_reference('something', 'delivered')


def test_should_return_none_if_no_statistics_for_a_service_for_a_day(sample_template, mmg_provider):
    data = _notification_json(sample_template)

    notification = Notification(**data)
    dao_create_notification(notification)
    assert not dao_get_notification_statistics_for_service_and_day(
        sample_template.service.id, (datetime.utcnow() - timedelta(days=1)).date())


def test_should_be_able_to_get_all_statistics_for_a_service(sample_template, mmg_provider):
    data = _notification_json(sample_template)

    notification_1 = Notification(**data)
    notification_2 = Notification(**data)
    notification_3 = Notification(**data)
    dao_create_notification(notification_1)
    dao_create_notification(notification_2)
    dao_create_notification(notification_3)


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
    assert notification_from_db.status == 'created'
    assert {'name': 'Jo'} == notification_from_db.personalisation


def test_save_notification_creates_sms(sample_template, sample_job, mmg_provider):
    assert Notification.query.count() == 0
    assert NotificationStatistics.query.count() == 0
    assert TemplateStatistics.query.count() == 0

    data = _notification_json(sample_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['job_id'] == notification_from_db.job_id
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['template_version'] == notification_from_db.template_version
    assert data['created_at'] == notification_from_db.created_at
    assert notification_from_db.status == 'created'


def test_save_notification_and_create_email(sample_email_template, sample_job, ses_provider):
    assert Notification.query.count() == 0
    assert NotificationStatistics.query.count() == 0
    assert TemplateStatistics.query.count() == 0

    data = _notification_json(sample_email_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['job_id'] == notification_from_db.job_id
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['template_version'] == notification_from_db.template_version
    assert data['created_at'] == notification_from_db.created_at
    assert notification_from_db.status == 'created'


def test_save_notification(sample_email_template, sample_job, ses_provider):
    assert Notification.query.count() == 0
    data = _notification_json(sample_email_template, job_id=sample_job.id)

    notification_1 = Notification(**data)
    notification_2 = Notification(**data)
    dao_create_notification(notification_1)

    assert Notification.query.count() == 1

    dao_create_notification(notification_2)

    assert Notification.query.count() == 2


def test_save_notification_creates_history(sample_email_template, sample_job):
    assert Notification.query.count() == 0
    data = _notification_json(sample_email_template, job_id=sample_job.id)

    notification_1 = Notification(**data)
    dao_create_notification(notification_1)

    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 1


def test_save_notification_with_test_api_key_does_not_create_history(sample_email_template, sample_api_key):
    assert Notification.query.count() == 0
    data = _notification_json(sample_email_template)
    data['key_type'] = KEY_TYPE_TEST
    data['api_key_id'] = sample_api_key.id

    notification_1 = Notification(**data)
    dao_create_notification(notification_1)

    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 0


def test_save_notification_with_research_mode_service_does_not_create_history(
        notify_db,
        notify_db_session):
    service = sample_service(notify_db, notify_db_session)
    service.research_mode = True
    dao_update_service(service)
    template = sample_template(notify_db, notify_db_session, service=service)

    assert Notification.query.count() == 0
    data = _notification_json(template)
    notification = Notification(**data)
    dao_create_notification(notification)
    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 0


def test_update_notification_with_test_api_key_does_not_update_or_create_history(sample_email_template, sample_api_key):
    assert Notification.query.count() == 0
    data = _notification_json(sample_email_template)
    data['key_type'] = KEY_TYPE_TEST
    data['api_key_id'] = sample_api_key.id

    notification = Notification(**data)
    dao_create_notification(notification)

    notification.status = 'delivered'
    dao_update_notification(notification)

    assert Notification.query.one().status == 'delivered'
    assert NotificationHistory.query.count() == 0


def test_update_notification_with_research_mode_service_does_not_create_or_update_history(
        notify_db,
        notify_db_session):
    service = sample_service(notify_db, notify_db_session)
    service.research_mode = True
    dao_update_service(service)
    template = sample_template(notify_db, notify_db_session, service=service)

    data = _notification_json(template)
    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 0

    notification.status = 'delivered'
    dao_update_notification(notification)

    assert Notification.query.one().status == 'delivered'
    assert NotificationHistory.query.count() == 0


def test_not_save_notification_and_not_create_stats_on_commit_error(sample_template, sample_job, mmg_provider):
    random_id = str(uuid.uuid4())

    assert Notification.query.count() == 0
    data = _notification_json(sample_template, job_id=random_id)

    notification = Notification(**data)
    with pytest.raises(SQLAlchemyError):
        dao_create_notification(notification)

    assert Notification.query.count() == 0
    assert Job.query.get(sample_job.id).notifications_sent == 0
    assert NotificationStatistics.query.count() == 0
    assert TemplateStatistics.query.count() == 0


def test_save_notification_and_increment_job(sample_template, sample_job, mmg_provider):
    assert Notification.query.count() == 0
    data = _notification_json(sample_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['job_id'] == notification_from_db.job_id
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['template_version'] == notification_from_db.template_version
    assert data['created_at'] == notification_from_db.created_at
    assert notification_from_db.status == 'created'

    notification_2 = Notification(**data)
    dao_create_notification(notification_2)
    assert Notification.query.count() == 2


def test_save_notification_and_increment_correct_job(notify_db, notify_db_session, sample_template, mmg_provider):
    from tests.app.conftest import sample_job
    job_1 = sample_job(notify_db, notify_db_session, sample_template.service)
    job_2 = sample_job(notify_db, notify_db_session, sample_template.service)

    assert Notification.query.count() == 0
    data = _notification_json(sample_template, job_id=job_1.id)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['job_id'] == notification_from_db.job_id
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['template_version'] == notification_from_db.template_version
    assert data['created_at'] == notification_from_db.created_at
    assert notification_from_db.status == 'created'
    assert job_1.id != job_2.id


def test_save_notification_with_no_job(sample_template, mmg_provider):
    assert Notification.query.count() == 0
    data = _notification_json(sample_template)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['template_version'] == notification_from_db.template_version
    assert data['created_at'] == notification_from_db.created_at
    assert notification_from_db.status == 'created'


def test_get_notification_by_id(notify_db, notify_db_session, sample_template):
    notification = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                       template=sample_template,
                                       scheduled_for='2017-05-05 14',
                                       status='created')
    notification_from_db = get_notification_with_personalisation(
        sample_template.service.id,
        notification.id,
        key_type=None
    )
    assert notification == notification_from_db
    assert notification_from_db.scheduled_notification.scheduled_for == datetime(2017, 5, 5, 14)


def test_get_notifications_by_reference(notify_db, notify_db_session, sample_service):
    client_reference = 'some-client-ref'
    assert len(Notification.query.all()) == 0
    sample_notification(notify_db, notify_db_session, client_reference=client_reference)
    sample_notification(notify_db, notify_db_session, client_reference=client_reference)
    sample_notification(notify_db, notify_db_session, client_reference='other-ref')
    all_notifications = get_notifications_for_service(sample_service.id, client_reference=client_reference).items
    assert len(all_notifications) == 2


def test_save_notification_no_job_id(sample_template, mmg_provider):
    assert Notification.query.count() == 0
    data = _notification_json(sample_template)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    notification_from_db = Notification.query.all()[0]
    assert notification_from_db.id
    assert data['to'] == notification_from_db.to
    assert data['service'] == notification_from_db.service
    assert data['template'] == notification_from_db.template
    assert data['template_version'] == notification_from_db.template_version
    assert notification_from_db.status == 'created'
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
        if status == 'failed':
            assert len(notifications(filter_dict={'status': status}).items) == len(NOTIFICATION_STATUS_TYPES_FAILED)
        else:
            assert len(notifications(filter_dict={'status': status}).items) == 1

    assert len(notifications(filter_dict={'status': NOTIFICATION_STATUS_TYPES[:3]}).items) == 3


def test_get_notification_billable_unit_count_per_month(notify_db, notify_db_session, sample_service):

    for year, month, day, hour, minute, second in (
        (2017, 1, 15, 23, 59, 59),  # ↓ 2016 financial year
        (2016, 9, 30, 23, 59, 59),  # counts in October with BST conversion
        (2016, 6, 30, 23, 50, 20),
        (2016, 7, 15, 9, 20, 25),
        (2016, 4, 1, 1, 1, 00),
        (2016, 4, 1, 0, 0, 00),
        (2016, 3, 31, 23, 00, 1),  # counts in April with BST conversion
        (2015, 4, 1, 13, 8, 59),  # ↓ 2015 financial year
        (2015, 11, 20, 22, 40, 45),
        (2016, 1, 31, 23, 30, 40)  # counts in January no BST conversion in winter
    ):
        sample_notification(
            notify_db, notify_db_session, service=sample_service,
            created_at=datetime(
                year, month, day, hour, minute, second, 0
            )
        )

    for financial_year, months in (
        (2017, []),
        (2016, [('April', 3), ('July', 2), ('October', 1), ('January', 1)]),
        (2015, [('April', 1), ('November', 1), ('January', 1)]),
        (2014, [])
    ):
        assert get_notification_billable_unit_count_per_month(
            sample_service.id, financial_year
        ) == months


def test_update_notification(sample_notification):
    assert sample_notification.status == 'created'
    sample_notification.status = 'failed'
    dao_update_notification(sample_notification)
    notification_from_db = Notification.query.get(sample_notification.id)
    assert notification_from_db.status == 'failed'


def test_update_notification_with_no_notification_status(sample_notification):
    # specifically, it has an old enum status, but not a new status (because the upgrade script has just run)
    update_dict = {'_status_enum': 'created', '_status_fkey': None}
    Notification.query.filter(Notification.id == sample_notification.id).update(update_dict)

    # now lets update the status to failed - both columns should now be populated
    sample_notification.status = 'failed'
    dao_update_notification(sample_notification)

    notification_from_db = Notification.query.get(sample_notification.id)
    assert notification_from_db.status == 'failed'
    assert notification_from_db._status_enum == 'failed'
    assert notification_from_db._status_fkey == 'failed'


def test_updating_notification_with_no_notification_status_updates_notification_history(sample_notification):
    # same as above, but with notification history
    update_dict = {'_status_enum': 'created', '_status_fkey': None}
    Notification.query.filter(Notification.id == sample_notification.id).update(update_dict)
    NotificationHistory.query.filter(NotificationHistory.id == sample_notification.id).update(update_dict)

    # now lets update the notification's status to failed - both columns should now be populated on the history object
    sample_notification.status = 'failed'
    dao_update_notification(sample_notification)

    hist_from_db = NotificationHistory.query.get(sample_notification.id)
    assert hist_from_db.status == 'failed'
    assert hist_from_db._status_enum == 'failed'
    assert hist_from_db._status_fkey == 'failed'


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


def test_should_delete_letter_notifications(sample_letter_template):
    should_delete = datetime.utcnow() - timedelta(days=8)

    create_notification(sample_letter_template, created_at=should_delete)

    delete_notifications_created_more_than_a_week_ago('created')
    assert len(Notification.query.all()) == 0


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


def test_creating_notification_adds_to_notification_history(sample_template):
    data = _notification_json(sample_template)
    notification = Notification(**data)

    dao_create_notification(notification)

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
    notification = Notification.query.one()
    hist1 = NotificationHistory.query.one()
    assert notification.id == sample_notification.id
    assert notification.status == "sending"
    assert hist1.id == sample_notification.id
    assert hist1.status == 'sending'


def test_should_delete_notification_and_notification_history_for_id(notify_db, notify_db_session, sample_template):
    data = _notification_json(sample_template)
    notification = Notification(**data)

    dao_create_notification(notification)

    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 1

    dao_delete_notifications_and_history_by_id(notification.id)

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0


def test_should_delete_notification_and_ignore_history_for_test_api(
        notify_db,
        notify_db_session,
        sample_email_template,
        sample_api_key):
    data = _notification_json(sample_email_template)
    data['key_type'] = KEY_TYPE_TEST
    data['api_key_id'] = sample_api_key.id

    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 0

    dao_delete_notifications_and_history_by_id(notification.id)

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0


def test_should_delete_notification_and_ignore_history_for_research_mode(notify_db, notify_db_session):
    service = sample_service(notify_db, notify_db_session)
    service.research_mode = True
    dao_update_service(service)
    template = sample_template(notify_db, notify_db_session, service=service)

    data = _notification_json(template)
    notification = Notification(**data)
    dao_create_notification(notification)

    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 0

    dao_delete_notifications_and_history_by_id(notification.id)

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0


def test_should_delete_only_notification_and_notification_history_with_id(notify_db, notify_db_session,
                                                                          sample_template):
    id_1 = uuid.uuid4()
    id_2 = uuid.uuid4()
    data_1 = _notification_json(sample_template, id=id_1)
    data_2 = _notification_json(sample_template, id=id_2)

    notification_1 = Notification(**data_1)
    notification_2 = Notification(**data_2)

    dao_create_notification(notification_1)
    dao_create_notification(notification_2)

    assert Notification.query.count() == 2
    assert NotificationHistory.query.count() == 2

    dao_delete_notifications_and_history_by_id(notification_1.id)

    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 1
    assert Notification.query.first().id == notification_2.id
    assert NotificationHistory.query.first().id == notification_2.id


def test_should_delete_no_notifications_or_notification_historys_if_no_matching_ids(
        notify_db,
        notify_db_session,
        sample_template
):
    id_1 = uuid.uuid4()
    id_2 = uuid.uuid4()
    data_1 = _notification_json(sample_template, id=id_1)

    notification_1 = Notification(**data_1)

    dao_create_notification(notification_1)

    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 1

    dao_delete_notifications_and_history_by_id(id_2)

    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 1


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


def test_dao_timeout_notifications(sample_template):
    with freeze_time(datetime.utcnow() - timedelta(minutes=2)):
        created = create_notification(sample_template, status='created')
        sending = create_notification(sample_template, status='sending')
        pending = create_notification(sample_template, status='pending')
        delivered = create_notification(sample_template, status='delivered')

    assert Notification.query.get(created.id).status == 'created'
    assert Notification.query.get(sending.id).status == 'sending'
    assert Notification.query.get(pending.id).status == 'pending'
    assert Notification.query.get(delivered.id).status == 'delivered'
    updated = dao_timeout_notifications(1)
    assert Notification.query.get(created.id).status == 'technical-failure'
    assert Notification.query.get(sending.id).status == 'temporary-failure'
    assert Notification.query.get(pending.id).status == 'temporary-failure'
    assert Notification.query.get(delivered.id).status == 'delivered'
    assert NotificationHistory.query.get(created.id).status == 'technical-failure'
    assert NotificationHistory.query.get(sending.id).status == 'temporary-failure'
    assert NotificationHistory.query.get(pending.id).status == 'temporary-failure'
    assert NotificationHistory.query.get(delivered.id).status == 'delivered'
    assert updated == 3


def test_dao_timeout_notifications_only_updates_for_older_notifications(sample_template):
    with freeze_time(datetime.utcnow() + timedelta(minutes=10)):
        created = create_notification(sample_template, status='created')
        sending = create_notification(sample_template, status='sending')
        pending = create_notification(sample_template, status='pending')
        delivered = create_notification(sample_template, status='delivered')

    assert Notification.query.get(created.id).status == 'created'
    assert Notification.query.get(sending.id).status == 'sending'
    assert Notification.query.get(pending.id).status == 'pending'
    assert Notification.query.get(delivered.id).status == 'delivered'
    updated = dao_timeout_notifications(1)
    assert NotificationHistory.query.get(created.id).status == 'created'
    assert NotificationHistory.query.get(sending.id).status == 'sending'
    assert NotificationHistory.query.get(pending.id).status == 'pending'
    assert NotificationHistory.query.get(delivered.id).status == 'delivered'
    assert updated == 0


def test_dao_timeout_notifications_doesnt_affect_letters(sample_letter_template):
    with freeze_time(datetime.utcnow() - timedelta(minutes=2)):
        created = create_notification(sample_letter_template, status='created')
        sending = create_notification(sample_letter_template, status='sending')
        pending = create_notification(sample_letter_template, status='pending')
        delivered = create_notification(sample_letter_template, status='delivered')

    assert Notification.query.get(created.id).status == 'created'
    assert Notification.query.get(sending.id).status == 'sending'
    assert Notification.query.get(pending.id).status == 'pending'
    assert Notification.query.get(delivered.id).status == 'delivered'

    updated = dao_timeout_notifications(1)

    assert NotificationHistory.query.get(created.id).status == 'created'
    assert NotificationHistory.query.get(sending.id).status == 'sending'
    assert NotificationHistory.query.get(pending.id).status == 'pending'
    assert NotificationHistory.query.get(delivered.id).status == 'delivered'
    assert updated == 0


def test_should_return_notifications_excluding_jobs_by_default(notify_db, notify_db_session, sample_service):
    assert len(Notification.query.all()) == 0

    job = sample_job(notify_db, notify_db_session)
    with_job = sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), status="delivered", job=job
    )
    without_job = sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), status="delivered"
    )

    all_notifications = Notification.query.all()
    assert len(all_notifications) == 2

    all_notifications = get_notifications_for_service(sample_service.id).items
    assert len(all_notifications) == 1
    assert all_notifications[0].id == without_job.id


def test_should_return_notifications_including_jobs(notify_db, notify_db_session, sample_service):
    assert len(Notification.query.all()) == 0

    job = sample_job(notify_db, notify_db_session)
    with_job = sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), status="delivered", job=job
    )

    all_notifications = Notification.query.all()
    assert len(all_notifications) == 1

    all_notifications = get_notifications_for_service(sample_service.id).items
    assert len(all_notifications) == 0

    all_notifications = get_notifications_for_service(sample_service.id, limit_days=1, include_jobs=True).items
    assert len(all_notifications) == 1
    assert all_notifications[0].id == with_job.id


def test_get_notifications_created_by_api_or_csv_are_returned_correctly_excluding_test_key_notifications(
        notify_db,
        notify_db_session,
        sample_service,
        sample_job,
        sample_api_key,
        sample_team_api_key,
        sample_test_api_key
):
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), job=sample_job
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_team_api_key.id,
        key_type=sample_team_api_key.key_type
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_test_api_key.id,
        key_type=sample_test_api_key.key_type
    )

    all_notifications = Notification.query.all()
    assert len(all_notifications) == 4

    # returns all real API derived notifications
    all_notifications = get_notifications_for_service(sample_service.id).items
    assert len(all_notifications) == 2

    # returns all API derived notifications, including those created with test key
    all_notifications = get_notifications_for_service(sample_service.id, include_from_test_key=True).items
    assert len(all_notifications) == 3

    # all real notifications including jobs
    all_notifications = get_notifications_for_service(sample_service.id, limit_days=1, include_jobs=True).items
    assert len(all_notifications) == 3


def test_get_notifications_with_a_live_api_key_type(
        notify_db,
        notify_db_session,
        sample_service,
        sample_job,
        sample_api_key,
        sample_team_api_key,
        sample_test_api_key
):
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), job=sample_job
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_team_api_key.id,
        key_type=sample_team_api_key.key_type
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_test_api_key.id,
        key_type=sample_test_api_key.key_type
    )

    all_notifications = Notification.query.all()
    assert len(all_notifications) == 4

    # only those created with normal API key, no jobs
    all_notifications = get_notifications_for_service(sample_service.id, limit_days=1, key_type=KEY_TYPE_NORMAL).items
    assert len(all_notifications) == 1

    # only those created with normal API key, with jobs
    all_notifications = get_notifications_for_service(sample_service.id, limit_days=1, include_jobs=True,
                                                      key_type=KEY_TYPE_NORMAL).items
    assert len(all_notifications) == 2


def test_get_notifications_with_a_test_api_key_type(
        notify_db,
        notify_db_session,
        sample_service,
        sample_job,
        sample_api_key,
        sample_team_api_key,
        sample_test_api_key
):
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), job=sample_job
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_team_api_key.id,
        key_type=sample_team_api_key.key_type
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_test_api_key.id,
        key_type=sample_test_api_key.key_type
    )

    # only those created with test API key, no jobs
    all_notifications = get_notifications_for_service(sample_service.id, limit_days=1, key_type=KEY_TYPE_TEST).items
    assert len(all_notifications) == 1

    # only those created with test API key, no jobs, even when requested
    all_notifications = get_notifications_for_service(sample_service.id, limit_days=1, include_jobs=True,
                                                      key_type=KEY_TYPE_TEST).items
    assert len(all_notifications) == 1


def test_get_notifications_with_a_team_api_key_type(
        notify_db,
        notify_db_session,
        sample_service,
        sample_job,
        sample_api_key,
        sample_team_api_key,
        sample_test_api_key
):
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), job=sample_job
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_team_api_key.id,
        key_type=sample_team_api_key.key_type
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_test_api_key.id,
        key_type=sample_test_api_key.key_type
    )

    # only those created with team API key, no jobs
    all_notifications = get_notifications_for_service(sample_service.id, limit_days=1, key_type=KEY_TYPE_TEAM).items
    assert len(all_notifications) == 1

    # only those created with team API key, no jobs, even when requested
    all_notifications = get_notifications_for_service(sample_service.id, limit_days=1, include_jobs=True,
                                                      key_type=KEY_TYPE_TEAM).items
    assert len(all_notifications) == 1


def test_should_exclude_test_key_notifications_by_default(
        notify_db,
        notify_db_session,
        sample_service,
        sample_job,
        sample_api_key,
        sample_team_api_key,
        sample_test_api_key
):
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), job=sample_job
    )

    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_team_api_key.id,
        key_type=sample_team_api_key.key_type
    )
    sample_notification(
        notify_db, notify_db_session, created_at=datetime.utcnow(), api_key_id=sample_test_api_key.id,
        key_type=sample_test_api_key.key_type
    )

    all_notifications = Notification.query.all()
    assert len(all_notifications) == 4

    all_notifications = get_notifications_for_service(sample_service.id, limit_days=1).items
    assert len(all_notifications) == 2

    all_notifications = get_notifications_for_service(sample_service.id, limit_days=1, include_jobs=True).items
    assert len(all_notifications) == 3

    all_notifications = get_notifications_for_service(sample_service.id, limit_days=1, key_type=KEY_TYPE_TEST).items
    assert len(all_notifications) == 1


@pytest.mark.parametrize('notification_type', ['sms', 'email'])
def test_get_total_sent_notifications_in_date_range_returns_only_in_date_range(
    notify_db,
    notify_db_session,
    sample_template,
    notification_type
):
    notification_history = partial(
        create_notification_history,
        notify_db,
        notify_db_session,
        sample_template,
        notification_type=notification_type,
        status='delivered'
    )

    start_date = datetime(2000, 3, 30, 0, 0, 0, 0)
    with freeze_time(start_date):
        notification_history(created_at=start_date + timedelta(hours=3))
        notification_history(created_at=start_date + timedelta(hours=5, minutes=10))
        notification_history(created_at=start_date + timedelta(hours=11, minutes=59))

    end_date = datetime(2000, 3, 31, 0, 0, 0, 0)
    notification_history(created_at=end_date + timedelta(seconds=1))
    notification_history(created_at=end_date + timedelta(minutes=10))

    total_count = get_total_sent_notifications_in_date_range(start_date, end_date, notification_type)
    assert total_count == 3


@pytest.mark.parametrize('notification_type', ['sms', 'email'])
def test_get_total_sent_notifications_in_date_range_excludes_test_key_notifications(
    notify_db,
    notify_db_session,
    sample_template,
    notification_type
):
    notification_history = partial(
        create_notification_history,
        notify_db,
        notify_db_session,
        sample_template,
        notification_type=notification_type,
        status='delivered'
    )

    start_date = datetime(2000, 3, 30, 0, 0, 0, 0)
    end_date = datetime(2000, 3, 31, 0, 0, 0, 0)
    with freeze_time(start_date):
        notification_history(key_type=KEY_TYPE_TEAM)
        notification_history(key_type=KEY_TYPE_TEAM)
        notification_history(key_type=KEY_TYPE_NORMAL)
        notification_history(key_type=KEY_TYPE_TEST)

    total_count = get_total_sent_notifications_in_date_range(start_date, end_date, notification_type)
    assert total_count == 3


def test_get_total_sent_notifications_for_sms_excludes_email_counts(
    notify_db,
    notify_db_session,
    sample_template
):
    notification_history = partial(
        create_notification_history,
        notify_db,
        notify_db_session,
        sample_template,
        status='delivered'
    )

    start_date = datetime(2000, 3, 30, 0, 0, 0, 0)
    end_date = datetime(2000, 3, 31, 0, 0, 0, 0)
    with freeze_time(start_date):
        notification_history(notification_type='email')
        notification_history(notification_type='email')
        notification_history(notification_type='sms')
        notification_history(notification_type='sms')
        notification_history(notification_type='sms')

    total_count = get_total_sent_notifications_in_date_range(start_date, end_date, 'sms')
    assert total_count == 3


def test_get_total_sent_notifications_for_email_excludes_sms_counts(
    notify_db,
    notify_db_session,
    sample_template
):
    notification_history = partial(
        create_notification_history,
        notify_db,
        notify_db_session,
        sample_template,
        status='delivered'
    )

    start_date = datetime(2000, 3, 30, 0, 0, 0, 0)
    end_date = datetime(2000, 3, 31, 0, 0, 0, 0)
    with freeze_time(start_date):
        notification_history(notification_type='email')
        notification_history(notification_type='email')
        notification_history(notification_type='sms')
        notification_history(notification_type='sms')
        notification_history(notification_type='sms')

    total_count = get_total_sent_notifications_in_date_range(start_date, end_date, 'email')
    assert total_count == 2


@freeze_time("2016-01-10 12:00:00.000000")
def test_slow_provider_delivery_returns_for_sent_notifications(
    sample_template
):
    now = datetime.utcnow()
    one_minute_from_now = now + timedelta(minutes=1)
    five_minutes_from_now = now + timedelta(minutes=5)

    notification_five_minutes_to_deliver = partial(
        create_notification,
        template=sample_template,
        status='delivered',
        sent_by='mmg',
        updated_at=five_minutes_from_now
    )

    notification_five_minutes_to_deliver(sent_at=now)
    notification_five_minutes_to_deliver(sent_at=one_minute_from_now)
    notification_five_minutes_to_deliver(sent_at=one_minute_from_now)

    slow_delivery = is_delivery_slow_for_provider(
        sent_at=one_minute_from_now,
        provider='mmg',
        threshold=2,
        delivery_time=timedelta(minutes=3),
        service_id=sample_template.service.id,
        template_id=sample_template.id
    )

    assert slow_delivery


@freeze_time("2016-01-10 12:00:00.000000")
def test_slow_provider_delivery_observes_threshold(
    sample_template
):
    now = datetime.utcnow()
    five_minutes_from_now = now + timedelta(minutes=5)

    notification_five_minutes_to_deliver = partial(
        create_notification,
        template=sample_template,
        status='delivered',
        sent_at=now,
        sent_by='mmg',
        updated_at=five_minutes_from_now
    )

    notification_five_minutes_to_deliver()
    notification_five_minutes_to_deliver()

    slow_delivery = is_delivery_slow_for_provider(
        sent_at=now,
        provider='mmg',
        threshold=3,
        delivery_time=timedelta(minutes=5),
        service_id=sample_template.service.id,
        template_id=sample_template.id
    )

    assert not slow_delivery


@freeze_time("2016-01-10 12:00:00.000000")
def test_slow_provider_delivery_returns_for_delivered_notifications_only(
    sample_template
):
    now = datetime.utcnow()
    five_minutes_from_now = now + timedelta(minutes=5)

    notification_five_minutes_to_deliver = partial(
        create_notification,
        template=sample_template,
        sent_at=now,
        sent_by='firetext',
        created_at=now,
        updated_at=five_minutes_from_now
    )

    notification_five_minutes_to_deliver(status='sending')
    notification_five_minutes_to_deliver(status='delivered')
    notification_five_minutes_to_deliver(status='delivered')

    slow_delivery = is_delivery_slow_for_provider(
        sent_at=now,
        provider='firetext',
        threshold=2,
        delivery_time=timedelta(minutes=5),
        service_id=sample_template.service.id,
        template_id=sample_template.id
    )

    assert slow_delivery


@freeze_time("2016-01-10 12:00:00.000000")
def test_slow_provider_delivery_does_not_return_for_standard_delivery_time(
    sample_template
):
    now = datetime.utcnow()
    five_minutes_from_now = now + timedelta(minutes=5)

    notification = partial(
        create_notification,
        template=sample_template,
        created_at=now,
        sent_at=now,
        sent_by='mmg',
        status='delivered'
    )

    notification(updated_at=five_minutes_from_now - timedelta(seconds=1))
    notification(updated_at=five_minutes_from_now - timedelta(seconds=1))
    notification(updated_at=five_minutes_from_now)

    slow_delivery = is_delivery_slow_for_provider(
        sent_at=now,
        provider='mmg',
        threshold=2,
        delivery_time=timedelta(minutes=5),
        service_id=sample_template.service.id,
        template_id=sample_template.id
    )

    assert not slow_delivery


def test_dao_update_notifications_sent_to_dvla(notify_db, notify_db_session, sample_letter_template):
    job = sample_job(notify_db=notify_db, notify_db_session=notify_db_session, template=sample_letter_template)
    notification = create_notification(template=sample_letter_template, job=job)

    updated_count = dao_update_notifications_sent_to_dvla(job_id=job.id, provider='some provider')

    assert updated_count == 1
    updated_notification = Notification.query.get(notification.id)
    assert updated_notification.status == 'sending'
    assert updated_notification.sent_by == 'some provider'
    assert updated_notification.sent_at
    assert updated_notification.updated_at
    history = NotificationHistory.query.get(notification.id)
    assert history.status == 'sending'
    assert history.sent_by == 'some provider'
    assert history.sent_at
    assert history.updated_at


def test_dao_update_notifications_sent_to_dvla_does_update_history_if_test_key(
        notify_db, notify_db_session, sample_letter_template, sample_api_key):
    job = sample_job(notify_db=notify_db, notify_db_session=notify_db_session, template=sample_letter_template)
    notification = create_notification(
        template=sample_letter_template, job=job, api_key_id=sample_api_key.id, key_type='test')

    updated_count = dao_update_notifications_sent_to_dvla(job_id=job.id, provider='some provider')

    assert updated_count == 1
    updated_notification = Notification.query.get(notification.id)
    assert updated_notification.status == 'sending'
    assert updated_notification.sent_by == 'some provider'
    assert updated_notification.sent_at
    assert updated_notification.updated_at
    assert not NotificationHistory.query.get(notification.id)


def test_dao_get_notifications_by_to_field(sample_template):
    notification1 = create_notification(template=sample_template, to_field='+447700900855')
    notification2 = create_notification(template=sample_template, to_field='jack@gmail.com')
    notification3 = create_notification(template=sample_template, to_field='jane@gmail.com')
    results = dao_get_notifications_by_to_field(notification1.service_id, "+447700900855")
    assert len(results) == 1
    assert results[0].id == notification1.id


def test_dao_get_notifications_by_to_field_search_is_not_case_sensitive(sample_template):
    notification1 = create_notification(template=sample_template, to_field='+447700900855')
    notification2 = create_notification(template=sample_template, to_field='jack@gmail.com')
    notification3 = create_notification(template=sample_template, to_field='jane@gmail.com')
    results = dao_get_notifications_by_to_field(notification1.service_id, 'JACK@gmail.com')
    assert len(results) == 1
    assert results[0].id == notification2.id


def test_dao_get_notifications_by_to_field_search_ignores_spaces(sample_template):
    notification1 = create_notification(template=sample_template, to_field='+447700900855')
    notification2 = create_notification(template=sample_template, to_field='+44 77 00900 855')
    notification3 = create_notification(template=sample_template, to_field=' +4477009 00 855 ')
    notification4 = create_notification(template=sample_template, to_field='jack@gmail.com')
    results = dao_get_notifications_by_to_field(notification1.service_id, '+447700900855')
    assert len(results) == 3
    assert notification1.id in [r.id for r in results]
    assert notification2.id in [r.id for r in results]
    assert notification3.id in [r.id for r in results]


def test_dao_created_scheduled_notification(sample_notification):

    scheduled_notification = ScheduledNotification(notification_id=sample_notification.id,
                                                   scheduled_for=datetime.strptime("2017-01-05 14", "%Y-%m-%d %H"))
    dao_created_scheduled_notification(scheduled_notification)
    saved_notification = ScheduledNotification.query.all()
    assert len(saved_notification) == 1
    assert saved_notification[0].notification_id == sample_notification.id
    assert saved_notification[0].scheduled_for == datetime(2017, 1, 5, 14)


def test_dao_get_scheduled_notifications(notify_db, notify_db_session, sample_template):
    notification_1 = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                         template=sample_template, scheduled_for='2017-05-05 14',
                                         status='created')
    sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                        template=sample_template, scheduled_for='2017-05-04 14', status='delivered')
    sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                        template=sample_template, status='created')
    scheduled_notifications = dao_get_scheduled_notifications()
    assert len(scheduled_notifications) == 1
    assert scheduled_notifications[0].id == notification_1.id
