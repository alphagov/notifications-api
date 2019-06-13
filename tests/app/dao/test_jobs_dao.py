import uuid
from datetime import datetime, timedelta
from functools import partial

import pytest
from freezegun import freeze_time

from app.dao.jobs_dao import (
    dao_get_job_by_service_id_and_job_id,
    dao_create_job,
    dao_update_job,
    dao_get_jobs_by_service_id,
    dao_set_scheduled_jobs_to_pending,
    dao_get_future_scheduled_job_by_id_and_service_id,
    dao_get_notification_outcomes_for_job,
    dao_get_jobs_older_than_data_retention,
    dao_cancel_letter_job
)
from app.models import (
    Job,
    EMAIL_TYPE, SMS_TYPE, LETTER_TYPE
)
from tests.app.db import create_job, create_service, create_template, create_notification


def test_should_have_decorated_notifications_dao_functions():
    assert dao_get_notification_outcomes_for_job.__wrapped__.__name__ == 'dao_get_notification_outcomes_for_job'  # noqa


def test_should_count_of_statuses_for_notifications_associated_with_job(sample_template, sample_job):
    create_notification(sample_template, job=sample_job, status='created')
    create_notification(sample_template, job=sample_job, status='created')
    create_notification(sample_template, job=sample_job, status='created')
    create_notification(sample_template, job=sample_job, status='sending')
    create_notification(sample_template, job=sample_job, status='delivered')

    results = dao_get_notification_outcomes_for_job(sample_template.service_id, sample_job.id)
    assert {row.status: row.count for row in results} == {
        'created': 3,
        'sending': 1,
        'delivered': 1,
    }


def test_should_return_zero_length_array_if_no_notifications_for_job(sample_service, sample_job):
    assert len(dao_get_notification_outcomes_for_job(sample_job.id, sample_service.id)) == 0


def test_should_return_notifications_only_for_this_job(sample_template):
    job_1 = create_job(sample_template)
    job_2 = create_job(sample_template)

    create_notification(sample_template, job=job_1, status='created')
    create_notification(sample_template, job=job_2, status='sent')

    results = dao_get_notification_outcomes_for_job(sample_template.service_id, job_1.id)
    assert {row.status: row.count for row in results} == {'created': 1}


def test_should_return_notifications_only_for_this_service(sample_notification_with_job):
    other_service = create_service(service_name='one')
    other_template = create_template(service=other_service)
    other_job = create_job(other_template)

    create_notification(other_template, job=other_job)

    assert len(dao_get_notification_outcomes_for_job(sample_notification_with_job.service_id, other_job.id)) == 0
    assert len(dao_get_notification_outcomes_for_job(other_service.id, sample_notification_with_job.id)) == 0


def test_create_sample_job(sample_template):
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
    job_from_db = Job.query.get(job_id)
    assert job == job_from_db
    assert job_from_db.notifications_delivered == 0
    assert job_from_db.notifications_failed == 0


def test_get_job_by_id(sample_job):
    job_from_db = dao_get_job_by_service_id_and_job_id(sample_job.service.id, sample_job.id)
    assert sample_job == job_from_db


def test_get_jobs_for_service(sample_template):
    one_job = create_job(sample_template)

    other_service = create_service(service_name="other service")
    other_template = create_template(service=other_service)
    other_job = create_job(other_template)

    one_job_from_db = dao_get_jobs_by_service_id(one_job.service_id).items
    other_job_from_db = dao_get_jobs_by_service_id(other_job.service_id).items

    assert len(one_job_from_db) == 1
    assert one_job == one_job_from_db[0]

    assert len(other_job_from_db) == 1
    assert other_job == other_job_from_db[0]

    assert one_job_from_db != other_job_from_db


def test_get_jobs_for_service_with_limit_days_param(sample_template):
    one_job = create_job(sample_template)
    old_job = create_job(sample_template, created_at=datetime.now() - timedelta(days=8))

    jobs = dao_get_jobs_by_service_id(one_job.service_id).items

    assert len(jobs) == 2
    assert one_job in jobs
    assert old_job in jobs

    jobs_limit_days = dao_get_jobs_by_service_id(one_job.service_id, limit_days=7).items
    assert len(jobs_limit_days) == 1
    assert one_job in jobs_limit_days
    assert old_job not in jobs_limit_days


@freeze_time('2017-06-10')
def test_get_jobs_for_service_with_limit_days_edge_case(sample_template):
    one_job = create_job(sample_template)
    just_after_midnight_job = create_job(sample_template, created_at=datetime(2017, 6, 2, 23, 0, 1))
    just_before_midnight_job = create_job(sample_template, created_at=datetime(2017, 6, 2, 22, 59, 0))

    jobs_limit_days = dao_get_jobs_by_service_id(one_job.service_id, limit_days=7).items
    assert len(jobs_limit_days) == 2
    assert one_job in jobs_limit_days
    assert just_after_midnight_job in jobs_limit_days
    assert just_before_midnight_job not in jobs_limit_days


def test_get_jobs_for_service_in_processed_at_then_created_at_order(notify_db, notify_db_session, sample_template):
    from_hour = partial(datetime, 2001, 1, 1)

    created_jobs = [
        create_job(sample_template, created_at=from_hour(2), processing_started=None),
        create_job(sample_template, created_at=from_hour(1), processing_started=None),
        create_job(sample_template, created_at=from_hour(1), processing_started=from_hour(4)),
        create_job(sample_template, created_at=from_hour(2), processing_started=from_hour(3)),
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


def test_set_scheduled_jobs_to_pending_gets_all_jobs_in_scheduled_state_before_now(sample_template):
    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
    one_hour_ago = datetime.utcnow() - timedelta(minutes=60)
    job_new = create_job(sample_template, scheduled_for=one_minute_ago, job_status='scheduled')
    job_old = create_job(sample_template, scheduled_for=one_hour_ago, job_status='scheduled')
    jobs = dao_set_scheduled_jobs_to_pending()
    assert len(jobs) == 2
    assert jobs[0].id == job_old.id
    assert jobs[1].id == job_new.id


def test_set_scheduled_jobs_to_pending_gets_ignores_jobs_not_scheduled(sample_template, sample_job):
    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
    job_scheduled = create_job(sample_template, scheduled_for=one_minute_ago, job_status='scheduled')
    jobs = dao_set_scheduled_jobs_to_pending()
    assert len(jobs) == 1
    assert jobs[0].id == job_scheduled.id


def test_set_scheduled_jobs_to_pending_gets_ignores_jobs_scheduled_in_the_future(sample_scheduled_job):
    jobs = dao_set_scheduled_jobs_to_pending()
    assert len(jobs) == 0


def test_set_scheduled_jobs_to_pending_updates_rows(sample_template):
    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
    one_hour_ago = datetime.utcnow() - timedelta(minutes=60)
    create_job(sample_template, scheduled_for=one_minute_ago, job_status='scheduled')
    create_job(sample_template, scheduled_for=one_hour_ago, job_status='scheduled')
    jobs = dao_set_scheduled_jobs_to_pending()
    assert len(jobs) == 2
    assert jobs[0].job_status == 'pending'
    assert jobs[1].job_status == 'pending'


def test_get_future_scheduled_job_gets_a_job_yet_to_send(sample_scheduled_job):
    result = dao_get_future_scheduled_job_by_id_and_service_id(sample_scheduled_job.id, sample_scheduled_job.service_id)
    assert result.id == sample_scheduled_job.id


@freeze_time('2016-10-31 10:00:00')
def test_should_get_jobs_seven_days_old(sample_template):
    """
    Jobs older than seven days are deleted, but only two day's worth (two-day window)
    """
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    within_seven_days = seven_days_ago + timedelta(seconds=1)

    eight_days_ago = seven_days_ago - timedelta(days=1)

    nine_days_ago = eight_days_ago - timedelta(days=2)
    nine_days_one_second_ago = nine_days_ago - timedelta(seconds=1)

    create_job(sample_template, created_at=seven_days_ago)
    create_job(sample_template, created_at=within_seven_days)
    job_to_delete = create_job(sample_template, created_at=eight_days_ago)
    create_job(sample_template, created_at=nine_days_ago, archived=True)
    create_job(sample_template, created_at=nine_days_one_second_ago, archived=True)

    jobs = dao_get_jobs_older_than_data_retention(notification_types=[sample_template.template_type])

    assert len(jobs) == 1
    assert jobs[0].id == job_to_delete.id


def test_get_jobs_for_service_is_paginated(notify_db, notify_db_session, sample_service, sample_template):
    with freeze_time('2015-01-01T00:00:00') as the_time:
        for _ in range(10):
            the_time.tick(timedelta(hours=1))
            create_job(sample_template)

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
        sample_template,
        sample_job,
        file_name,
):
    create_job(sample_template, original_file_name=file_name,)

    jobs = dao_get_jobs_by_service_id(sample_job.service_id).items

    assert jobs == [sample_job]


@freeze_time('2016-10-31 10:00:00')
def test_should_get_jobs_seven_days_old_filters_type(sample_service):
    eight_days_ago = datetime.utcnow() - timedelta(days=8)
    letter_template = create_template(sample_service, template_type=LETTER_TYPE)
    sms_template = create_template(sample_service, template_type=SMS_TYPE)
    email_template = create_template(sample_service, template_type=EMAIL_TYPE)

    job_to_remain = create_job(letter_template, created_at=eight_days_ago)
    create_job(sms_template, created_at=eight_days_ago)
    create_job(email_template, created_at=eight_days_ago)

    jobs = dao_get_jobs_older_than_data_retention(
        notification_types=[EMAIL_TYPE, SMS_TYPE]
    )

    assert len(jobs) == 2
    assert job_to_remain.id not in [job.id for job in jobs]


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


@freeze_time('2019-06-13 13:00')
def test_dao_cancel_letter_job_updates_notifications_and_job_to_cancelled(sample_letter_template):
    job = create_job(template=sample_letter_template, notification_count=1, job_status='finished')
    notification = create_notification(template=job.template, job=job, status='created')
    assert dao_cancel_letter_job(job) == 1
    assert notification.status == 'cancelled'
    assert job.job_status == 'cancelled'


@freeze_time('2019-06-13 13:00')
def test_dao_cancel_letter_job_does_not_allow_cancel_if_notification_in_sending(sample_letter_template):
    job = create_job(template=sample_letter_template, notification_count=2, job_status='finished')
    letter_1 = create_notification(template=job.template, job=job, status='sending')
    letter_2 = create_notification(template=job.template, job=job, status='created')
    assert not dao_cancel_letter_job(job)
    assert letter_1.status == 'sending'
    assert letter_2.status == 'created'
    assert job.job_status == 'finished'


def test_dao_cancel_letter_job_does_not_allow_cancel_if_letters_already_sent_to_dvla(sample_letter_template):
    with freeze_time('2019-06-13 13:00'):
        job = create_job(template=sample_letter_template, notification_count=1, job_status='finished')
        letter = create_notification(template=job.template, job=job, status='created')

    with freeze_time('2019-06-13 17:32'):
        assert not dao_cancel_letter_job(job)
    assert letter.status == 'created'
    assert job.job_status == 'finished'


@freeze_time('2019-06-13 13:00')
def test_dao_cancel_letter_job_does_not_allow_cancel_if_not_a_letter_job(sample_template):
    job = create_job(template=sample_template, notification_count=1, job_status='finished')
    notification = create_notification(template=job.template, job=job, status='created')
    assert not dao_cancel_letter_job(job)
    assert notification.status == 'created'
    assert job.job_status == 'finished'


@freeze_time('2019-06-13 13:00')
def test_dao_cancel_letter_job_does_not_allow_cancel_if_job_not_finished(sample_letter_template):
    job = create_job(template=sample_letter_template, notification_count=1, job_status="finished")
    create_notification(template=job.template, job=job, status='created')
    assert not dao_cancel_letter_job(job)


@freeze_time('2019-06-13 13:00')
def test_dao_cancel_letter_job_does_not_allow_cancel_if_notifications_not_in_db_yet(sample_letter_template):
    job = create_job(template=sample_letter_template, notification_count=2, job_status='finished')
    create_notification(template=job.template, job=job, status='created')
    assert not dao_cancel_letter_job(job)
