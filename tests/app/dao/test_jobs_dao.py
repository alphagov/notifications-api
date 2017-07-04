from datetime import datetime, timedelta
from functools import partial
import pytest
import uuid

from freezegun import freeze_time

from app.dao.jobs_dao import (
    dao_get_job_by_service_id_and_job_id,
    dao_create_job,
    dao_update_job,
    dao_get_jobs_by_service_id,
    dao_set_scheduled_jobs_to_pending,
    dao_get_future_scheduled_job_by_id_and_service_id,
    dao_get_notification_outcomes_for_job,
    all_notifications_are_created_for_job,
    dao_update_job_status,
    dao_get_all_notifications_for_job,
    dao_get_jobs_older_than_limited_by,
    dao_get_job_statistics_for_job,
    dao_get_job_stats_for_service)
from app.dao.statistics_dao import create_or_update_job_sending_statistics, update_job_stats_outcome_count
from app.models import (
    Job, JobStatistics,
    EMAIL_TYPE, SMS_TYPE, LETTER_TYPE
)

from tests.app.conftest import sample_notification as create_notification
from tests.app.conftest import sample_job as create_job
from tests.app.conftest import sample_service as create_service
from tests.app.conftest import sample_template as create_template
from tests.app.db import create_user


def test_should_have_decorated_notifications_dao_functions():
    assert dao_get_notification_outcomes_for_job.__wrapped__.__name__ == 'dao_get_notification_outcomes_for_job'  # noqa


def test_should_get_all_statuses_for_notifications_associated_with_job(
        notify_db,
        notify_db_session,
        sample_service,
        sample_job):
    notification = partial(create_notification, notify_db, notify_db_session, service=sample_service, job=sample_job)
    notification(status='created')
    notification(status='sending')
    notification(status='delivered')
    notification(status='pending')
    notification(status='failed')
    notification(status='technical-failure')
    notification(status='temporary-failure')
    notification(status='permanent-failure')
    notification(status='sent')

    results = dao_get_notification_outcomes_for_job(sample_service.id, sample_job.id)
    assert [(row.count, row.status) for row in results] == [
        (1, 'created'),
        (1, 'sending'),
        (1, 'delivered'),
        (1, 'pending'),
        (1, 'failed'),
        (1, 'technical-failure'),
        (1, 'temporary-failure'),
        (1, 'permanent-failure'),
        (1, 'sent')
    ]


def test_should_count_of_statuses_for_notifications_associated_with_job(
        notify_db,
        notify_db_session,
        sample_service,
        sample_job):
    notification = partial(create_notification, notify_db, notify_db_session, service=sample_service, job=sample_job)
    notification(status='created')
    notification(status='created')
    notification(status='sending')
    notification(status='sending')
    notification(status='sending')
    notification(status='sending')
    notification(status='delivered')
    notification(status='delivered')

    results = dao_get_notification_outcomes_for_job(sample_service.id, sample_job.id)
    assert [(row.count, row.status) for row in results] == [
        (2, 'created'),
        (4, 'sending'),
        (2, 'delivered')
    ]


def test_should_return_zero_length_array_if_no_notifications_for_job(sample_service, sample_job):
    assert len(dao_get_notification_outcomes_for_job(sample_job.id, sample_service.id)) == 0


def test_should_return_notifications_only_for_this_job(notify_db, notify_db_session, sample_service):
    job_1 = create_job(notify_db, notify_db_session, service=sample_service)
    job_2 = create_job(notify_db, notify_db_session, service=sample_service)

    create_notification(notify_db, notify_db_session, service=sample_service, job=job_1, status='created')
    create_notification(notify_db, notify_db_session, service=sample_service, job=job_2, status='created')

    results = dao_get_notification_outcomes_for_job(sample_service.id, job_1.id)
    assert [(row.count, row.status) for row in results] == [
        (1, 'created')
    ]


def test_should_return_notifications_only_for_this_service(notify_db, notify_db_session):
    service_1 = create_service(notify_db, notify_db_session, service_name="one", email_from="one")
    service_2 = create_service(notify_db, notify_db_session, service_name="two", email_from="two")

    job_1 = create_job(notify_db, notify_db_session, service=service_1)
    job_2 = create_job(notify_db, notify_db_session, service=service_2)

    create_notification(notify_db, notify_db_session, service=service_1, job=job_1, status='created')
    create_notification(notify_db, notify_db_session, service=service_2, job=job_2, status='created')

    assert len(dao_get_notification_outcomes_for_job(service_1.id, job_2.id)) == 0


def test_create_job(sample_template):
    assert Job.query.count() == 0

    job_id = uuid.uuid4()
    data = {
        'id': job_id,
        'service_id': sample_template.service.id,
        'template_id': sample_template.id,
        'template_version': sample_template.version,
        'original_file_name': 'some.csv',
        'notification_count': 1,
        'created_by': sample_template.created_by
    }

    job = Job(**data)
    dao_create_job(job)

    assert Job.query.count() == 1
    assert JobStatistics.query.count() == 1
    job_from_db = Job.query.get(job_id)
    assert job == job_from_db
    assert job_from_db.notifications_delivered == 0
    assert job_from_db.notifications_failed == 0
    job_stats_from_db = JobStatistics.query.filter_by(job_id=job_id).all()
    assert len(job_stats_from_db) == 1
    assert job_stats_from_db[0].sms_sent == 0
    assert job_stats_from_db[0].emails_sent == 0
    assert job_stats_from_db[0].letters_sent == 0

    assert job_stats_from_db[0].sms_failed == 0
    assert job_stats_from_db[0].emails_failed == 0
    assert job_stats_from_db[0].letters_failed == 0

    assert job_stats_from_db[0].sms_delivered == 0
    assert job_stats_from_db[0].emails_delivered == 0


def test_get_job_by_id(sample_job):
    job_from_db = dao_get_job_by_service_id_and_job_id(sample_job.service.id, sample_job.id)
    assert sample_job == job_from_db


def test_get_jobs_for_service(notify_db, notify_db_session, sample_template):
    one_job = create_job(notify_db, notify_db_session, sample_template.service, sample_template)

    other_user = create_user(email="test@digital.cabinet-office.gov.uk")
    other_service = create_service(notify_db, notify_db_session, user=other_user, service_name="other service",
                                   email_from='other.service')
    other_template = create_template(notify_db, notify_db_session, service=other_service)
    other_job = create_job(notify_db, notify_db_session, service=other_service, template=other_template)

    one_job_from_db = dao_get_jobs_by_service_id(one_job.service_id).items
    other_job_from_db = dao_get_jobs_by_service_id(other_job.service_id).items

    assert len(one_job_from_db) == 1
    assert one_job == one_job_from_db[0]

    assert len(other_job_from_db) == 1
    assert other_job == other_job_from_db[0]

    assert one_job_from_db != other_job_from_db


def test_get_jobs_for_service_with_limit_days_param(notify_db, notify_db_session, sample_template):
    one_job = create_job(notify_db, notify_db_session, sample_template.service, sample_template)
    old_job = create_job(notify_db, notify_db_session, sample_template.service, sample_template,
                         created_at=datetime.now() - timedelta(days=8))

    jobs = dao_get_jobs_by_service_id(one_job.service_id).items

    assert len(jobs) == 2
    assert one_job in jobs
    assert old_job in jobs

    jobs_limit_days = dao_get_jobs_by_service_id(one_job.service_id, limit_days=7).items
    assert len(jobs_limit_days) == 1
    assert one_job in jobs_limit_days
    assert old_job not in jobs_limit_days


def test_get_jobs_for_service_with_limit_days_edge_case(notify_db, notify_db_session, sample_template):
    one_job = create_job(notify_db, notify_db_session, sample_template.service, sample_template)
    job_two = create_job(notify_db, notify_db_session, sample_template.service, sample_template,
                         created_at=(datetime.now() - timedelta(days=7)).date())
    one_second_after_midnight = datetime.combine((datetime.now() - timedelta(days=7)).date(),
                                                 datetime.strptime("000001", "%H%M%S").time())
    just_after_midnight_job = create_job(notify_db, notify_db_session, sample_template.service, sample_template,
                                         created_at=one_second_after_midnight)
    job_eight_days_old = create_job(notify_db, notify_db_session, sample_template.service, sample_template,
                                    created_at=datetime.now() - timedelta(days=8))

    jobs_limit_days = dao_get_jobs_by_service_id(one_job.service_id, limit_days=7).items
    assert len(jobs_limit_days) == 3
    assert one_job in jobs_limit_days
    assert job_two in jobs_limit_days
    assert just_after_midnight_job in jobs_limit_days
    assert job_eight_days_old not in jobs_limit_days


def test_get_jobs_for_service_in_processed_at_then_created_at_order(notify_db, notify_db_session, sample_template):

    _create_job = partial(create_job, notify_db, notify_db_session, sample_template.service, sample_template)
    from_hour = partial(datetime, 2001, 1, 1)

    created_jobs = [
        _create_job(created_at=from_hour(2), processing_started=None),
        _create_job(created_at=from_hour(1), processing_started=None),
        _create_job(created_at=from_hour(1), processing_started=from_hour(4)),
        _create_job(created_at=from_hour(2), processing_started=from_hour(3)),
    ]

    jobs = dao_get_jobs_by_service_id(sample_template.service.id).items

    assert len(jobs) == len(created_jobs)

    for index in range(0, len(created_jobs)):
        assert jobs[index].id == created_jobs[index].id


def test_update_job(sample_job):
    assert sample_job.job_status == 'pending'

    sample_job.job_status = 'in progress'

    dao_update_job(sample_job)

    job_from_db = Job.query.get(sample_job.id)

    assert job_from_db.job_status == 'in progress'


def test_set_scheduled_jobs_to_pending_gets_all_jobs_in_scheduled_state_before_now(notify_db, notify_db_session):
    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
    one_hour_ago = datetime.utcnow() - timedelta(minutes=60)
    job_new = create_job(notify_db, notify_db_session, scheduled_for=one_minute_ago, job_status='scheduled')
    job_old = create_job(notify_db, notify_db_session, scheduled_for=one_hour_ago, job_status='scheduled')
    jobs = dao_set_scheduled_jobs_to_pending()
    assert len(jobs) == 2
    assert jobs[0].id == job_old.id
    assert jobs[1].id == job_new.id


def test_set_scheduled_jobs_to_pending_gets_ignores_jobs_not_scheduled(notify_db, notify_db_session):
    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
    create_job(notify_db, notify_db_session)
    job_scheduled = create_job(notify_db, notify_db_session, scheduled_for=one_minute_ago, job_status='scheduled')
    jobs = dao_set_scheduled_jobs_to_pending()
    assert len(jobs) == 1
    assert jobs[0].id == job_scheduled.id


def test_set_scheduled_jobs_to_pending_gets_ignores_jobs_scheduled_in_the_future(sample_scheduled_job):
    jobs = dao_set_scheduled_jobs_to_pending()
    assert len(jobs) == 0


def test_set_scheduled_jobs_to_pending_updates_rows(notify_db, notify_db_session):
    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
    one_hour_ago = datetime.utcnow() - timedelta(minutes=60)
    create_job(notify_db, notify_db_session, scheduled_for=one_minute_ago, job_status='scheduled')
    create_job(notify_db, notify_db_session, scheduled_for=one_hour_ago, job_status='scheduled')
    jobs = dao_set_scheduled_jobs_to_pending()
    assert len(jobs) == 2
    assert jobs[0].job_status == 'pending'
    assert jobs[1].job_status == 'pending'


def test_get_future_scheduled_job_gets_a_job_yet_to_send(sample_scheduled_job):
    result = dao_get_future_scheduled_job_by_id_and_service_id(sample_scheduled_job.id, sample_scheduled_job.service_id)
    assert result.id == sample_scheduled_job.id


@freeze_time('2016-10-31 10:00:00')
def test_should_get_jobs_seven_days_old(notify_db, notify_db_session, sample_template):
    """
    Jobs older than seven days are deleted, but only two day's worth (two-day window)
    """
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    within_seven_days = seven_days_ago + timedelta(seconds=1)

    eight_days_ago = seven_days_ago - timedelta(days=1)

    nine_days_ago = eight_days_ago - timedelta(days=2)
    nine_days_one_second_ago = nine_days_ago - timedelta(seconds=1)

    job = partial(create_job, notify_db, notify_db_session)
    job(created_at=seven_days_ago)
    job(created_at=within_seven_days)
    job_to_delete = job(created_at=eight_days_ago)
    job(created_at=nine_days_ago)
    job(created_at=nine_days_one_second_ago)

    jobs = dao_get_jobs_older_than_limited_by(job_types=[sample_template.template_type])

    assert len(jobs) == 1
    assert jobs[0].id == job_to_delete.id


def test_get_jobs_for_service_is_paginated(notify_db, notify_db_session, sample_service, sample_template):
    with freeze_time('2015-01-01T00:00:00') as the_time:
        for _ in range(10):
            the_time.tick(timedelta(hours=1))
            create_job(notify_db, notify_db_session, sample_service, sample_template)

    res = dao_get_jobs_by_service_id(sample_service.id, page=1, page_size=2)

    assert res.per_page == 2
    assert res.total == 10
    assert len(res.items) == 2
    assert res.items[0].created_at == datetime(2015, 1, 1, 10)
    assert res.items[1].created_at == datetime(2015, 1, 1, 9)

    res = dao_get_jobs_by_service_id(sample_service.id, page=2, page_size=2)

    assert len(res.items) == 2
    assert res.items[0].created_at == datetime(2015, 1, 1, 8)
    assert res.items[1].created_at == datetime(2015, 1, 1, 7)


@pytest.mark.parametrize('file_name', [
    'Test message',
    'Report',
])
def test_get_jobs_for_service_doesnt_return_test_messages(
    notify_db,
    notify_db_session,
    sample_template,
    sample_job,
    file_name,
):
    test_job = create_job(
        notify_db,
        notify_db_session,
        sample_template.service,
        sample_template,
        original_file_name=file_name,
    )

    jobs = dao_get_jobs_by_service_id(sample_job.service_id).items

    assert jobs == [sample_job]


def test_all_notifications_are_created_for_job_returns_true(notify_db, notify_db_session):
    job = create_job(notify_db=notify_db, notify_db_session=notify_db_session, notification_count=2)
    create_notification(notify_db=notify_db, notify_db_session=notify_db_session, job=job)
    create_notification(notify_db=notify_db, notify_db_session=notify_db_session, job=job)
    job_is_complete = all_notifications_are_created_for_job(job.id)
    assert job_is_complete


def test_all_notifications_are_created_for_job_returns_false(notify_db, notify_db_session):
    job = create_job(notify_db=notify_db, notify_db_session=notify_db_session, notification_count=2)
    job_is_complete = all_notifications_are_created_for_job(job.id)
    assert not job_is_complete


def test_are_all_notifications_created_for_job_returns_false_when_job_does_not_exist():
    job_is_complete = all_notifications_are_created_for_job(uuid.uuid4())
    assert not job_is_complete


def test_dao_get_all_notifications_for_job(notify_db, notify_db_session, sample_job):
    create_notification(notify_db=notify_db, notify_db_session=notify_db_session, job=sample_job)
    create_notification(notify_db=notify_db, notify_db_session=notify_db_session, job=sample_job)
    create_notification(notify_db=notify_db, notify_db_session=notify_db_session, job=sample_job)

    assert len(dao_get_all_notifications_for_job(sample_job.id)) == 3


def test_dao_update_job_status(sample_job):
    dao_update_job_status(sample_job.id, 'sent to dvla')
    updated_job = Job.query.get(sample_job.id)
    assert updated_job.job_status == 'sent to dvla'
    assert updated_job.updated_at


@freeze_time('2016-10-31 10:00:00')
def test_should_get_jobs_seven_days_old_filters_type(notify_db, notify_db_session):
    eight_days_ago = datetime.utcnow() - timedelta(days=8)
    letter_template = create_template(notify_db, notify_db_session, template_type=LETTER_TYPE)
    sms_template = create_template(notify_db, notify_db_session, template_type=SMS_TYPE)
    email_template = create_template(notify_db, notify_db_session, template_type=EMAIL_TYPE)

    job = partial(create_job, notify_db, notify_db_session, created_at=eight_days_ago)
    job_to_remain = job(template=letter_template)
    job(template=sms_template)
    job(template=email_template)

    jobs = dao_get_jobs_older_than_limited_by(
        job_types=[EMAIL_TYPE, SMS_TYPE]
    )

    assert len(jobs) == 2
    assert job_to_remain.id not in [job.id for job in jobs]


def test_dao_get_job_statistics_for_job(notify_db, notify_db_session, sample_job):
    notification = create_notification(notify_db=notify_db, notify_db_session=notify_db_session, job=sample_job)
    notification_delivered = create_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                                 job=sample_job, status='delivered')
    notification_failed = create_notification(notify_db=notify_db, notify_db_session=notify_db_session, job=sample_job,
                                              status='permanent-failure')

    create_or_update_job_sending_statistics(notification)
    create_or_update_job_sending_statistics(notification_delivered)
    create_or_update_job_sending_statistics(notification_failed)
    update_job_stats_outcome_count(notification_delivered)
    update_job_stats_outcome_count(notification_failed)
    result = dao_get_job_statistics_for_job(sample_job.service_id, sample_job.id)
    assert_job_stat(job=sample_job, result=result, sent=3, delivered=1, failed=1)


def test_dao_get_job_statistics_for_job(notify_db, notify_db_session, sample_service):
    job_1, job_2 = stats_set_up(notify_db, notify_db_session, sample_service)
    result = dao_get_job_statistics_for_job(sample_service.id, job_1.id)
    assert_job_stat(job=job_1, result=result, sent=2, delivered=1, failed=0)

    result_2 = dao_get_job_statistics_for_job(sample_service.id, job_2.id)
    assert_job_stat(job=job_2, result=result_2, sent=1, delivered=0, failed=1)


def test_dao_get_job_stats_for_service(notify_db, notify_db_session, sample_service):
    job_1, job_2 = stats_set_up(notify_db, notify_db_session, sample_service)

    results = dao_get_job_stats_for_service(sample_service.id).items
    assert len(results) == 2
    assert_job_stat(job_2, results[0], 1, 0, 1)
    assert_job_stat(job_1, results[1], 2, 1, 0)


def test_dao_get_job_stats_for_service_only_returns_stats_for_service(notify_db, notify_db_session, sample_service):
    job_1, job_2 = stats_set_up(notify_db, notify_db_session, sample_service)
    another_service = create_service(notify_db=notify_db, notify_db_session=notify_db_session,
                                     service_name='Another Service')
    job_3, job_4 = stats_set_up(notify_db, notify_db_session, service=another_service)

    results = dao_get_job_stats_for_service(sample_service.id).items
    assert len(results) == 2
    assert_job_stat(job_2, results[0], 1, 0, 1)
    assert_job_stat(job_1, results[1], 2, 1, 0)

    results = dao_get_job_stats_for_service(another_service.id).items
    assert len(results) == 2
    assert_job_stat(job_4, results[0], 1, 0, 1)
    assert_job_stat(job_3, results[1], 2, 1, 0)


def test_dao_get_job_stats_for_service_only_returns_jobs_created_within_limited_days(
        notify_db, notify_db_session, sample_service):
    job_1, job_2 = stats_set_up(notify_db, notify_db_session, sample_service)

    results = dao_get_job_stats_for_service(sample_service.id, limit_days=1)
    assert results.total == 1
    assert_job_stat(job_2, results.items[0], 1, 0, 1)


def test_dao_get_job_stats_for_service_only_returns_jobs_created_within_limited_days_inclusive(
        notify_db, notify_db_session, sample_service):
    job_1, job_2 = stats_set_up(notify_db, notify_db_session, sample_service)

    results = dao_get_job_stats_for_service(sample_service.id, limit_days=2).items
    assert len(results) == 2
    assert_job_stat(job_2, results[0], 1, 0, 1)
    assert_job_stat(job_1, results[1], 2, 1, 0)


def test_dao_get_job_stats_paginates_results(
        notify_db, notify_db_session, sample_service):
    job_1, job_2 = stats_set_up(notify_db, notify_db_session, sample_service)

    results = dao_get_job_stats_for_service(sample_service.id, page=1, page_size=1).items
    assert len(results) == 1
    assert_job_stat(job_2, results[0], 1, 0, 1)
    results_2 = dao_get_job_stats_for_service(sample_service.id, page=2, page_size=1).items
    assert len(results_2) == 1
    assert_job_stat(job_1, results_2[0], 2, 1, 0)


def test_dao_get_job_returns_jobs_for_status(
        notify_db, notify_db_session, sample_service):
    stats_set_up(notify_db, notify_db_session, sample_service)

    results = dao_get_job_stats_for_service(sample_service.id, statuses=['pending'])
    assert results.total == 1
    results_2 = dao_get_job_stats_for_service(sample_service.id, statuses=['pending', 'finished'])
    assert results_2.total == 2


def assert_job_stat(job, result, sent, delivered, failed):
    assert result.job_id == job.id
    assert result.original_file_name == job.original_file_name
    assert result.created_at == job.created_at
    assert result.scheduled_for == job.scheduled_for
    assert result.template_id == job.template_id
    assert result.template_version == job.template_version
    assert result.job_status == job.job_status
    assert result.service_id == job.service_id
    assert result.notification_count == job.notification_count
    assert result.sent == sent
    assert result.delivered == delivered
    assert result.failed == failed


def stats_set_up(notify_db, notify_db_session, service):
    job_1 = create_job(notify_db=notify_db, notify_db_session=notify_db_session,
                       service=service, created_at=datetime.utcnow() - timedelta(days=2))
    job_2 = create_job(notify_db=notify_db, notify_db_session=notify_db_session,
                       service=service, original_file_name='Another job', job_status='finished')
    notification = create_notification(notify_db=notify_db, notify_db_session=notify_db_session, job=job_1)
    notification_delivered = create_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                                 job=job_1, status='delivered')
    notification_failed = create_notification(notify_db=notify_db, notify_db_session=notify_db_session, job=job_2,
                                              status='permanent-failure')
    create_or_update_job_sending_statistics(notification)
    create_or_update_job_sending_statistics(notification_delivered)
    create_or_update_job_sending_statistics(notification_failed)
    update_job_stats_outcome_count(notification_delivered)
    update_job_stats_outcome_count(notification_failed)
    return job_1, job_2
