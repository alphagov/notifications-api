from datetime import datetime, timedelta
from unittest.mock import call

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.dao.statistics_dao import (
    create_or_update_job_sending_statistics,
    update_job_stats_outcome_count,
    dao_timeout_job_statistics)
from app.models import (
    JobStatistics,
    SMS_TYPE,
    EMAIL_TYPE,
    LETTER_TYPE,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_PENDING, NOTIFICATION_CREATED, NOTIFICATION_FAILED, NOTIFICATION_SENT, NOTIFICATION_SENDING,
    NOTIFICATION_STATUS_TYPES_COMPLETED, Notification, NOTIFICATION_STATUS_TYPES, NOTIFICATION_STATUS_SUCCESS)
from tests.app.conftest import sample_notification, sample_email_template, sample_template, sample_job, sample_service


@pytest.mark.parametrize('notification_type, sms_count, email_count, letter_count', [
    (SMS_TYPE, 1, 0, 0),
    (EMAIL_TYPE, 0, 1, 0),
    (LETTER_TYPE, 0, 0, 1)
])
def test_should_create_a_stats_entry_for_a_job(
        notify_db,
        notify_db_session,
        sample_job,
        sample_letter_template,
        notification_type,
        sms_count,
        email_count,
        letter_count
):
    template = None

    if notification_type == SMS_TYPE:
        template = sample_template(notify_db, notify_db_session, service=sample_job.service)

    if notification_type == EMAIL_TYPE:
        template = sample_email_template(notify_db, notify_db_session, service=sample_job.service)

    if notification_type == LETTER_TYPE:
        template = sample_letter_template

    notification = sample_notification(
        notify_db, notify_db_session, service=sample_job.service, template=template, job=sample_job
    )

    create_or_update_job_sending_statistics(notification)

    stats = JobStatistics.query.all()

    assert len(stats) == 1

    stat = stats[0]
    assert stat.job_id == sample_job.id

    assert stat.emails_sent == email_count
    assert stat.sms_sent == sms_count
    assert stat.letters_sent == letter_count

    assert stat.emails_delivered == 0
    assert stat.emails_failed == 0
    assert stat.sms_delivered == 0
    assert stat.sms_failed == 0
    assert stat.letters_failed == 0


@pytest.mark.parametrize('notification_type, sms_count, email_count, letter_count', [
    (SMS_TYPE, 2, 0, 0),
    (EMAIL_TYPE, 0, 2, 0),
    (LETTER_TYPE, 0, 0, 2)
])
def test_should_update_a_stats_entry_for_a_job(
        notify_db,
        notify_db_session,
        sample_job,
        sample_letter_template,
        notification_type,
        sms_count,
        email_count,
        letter_count
):
    template = None

    if notification_type == SMS_TYPE:
        template = sample_template(notify_db, notify_db_session, service=sample_job.service)

    if notification_type == EMAIL_TYPE:
        template = sample_email_template(notify_db, notify_db_session, service=sample_job.service)

    if notification_type == LETTER_TYPE:
        template = sample_letter_template

    notification = sample_notification(
        notify_db, notify_db_session, service=sample_job.service, template=template, job=sample_job
    )

    create_or_update_job_sending_statistics(notification)

    stats = JobStatistics.query.all()

    assert len(stats) == 1

    create_or_update_job_sending_statistics(notification)

    stat = stats[0]
    assert stat.job_id == sample_job.id

    assert stat.emails_sent == email_count
    assert stat.sms_sent == sms_count
    assert stat.letters_sent == letter_count

    assert stat.emails_delivered == 0
    assert stat.emails_failed == 0
    assert stat.sms_delivered == 0
    assert stat.sms_failed == 0
    assert stat.letters_failed == 0


def test_should_handle_error_conditions(
        notify_db,
        notify_db_session,
        sample_job,
        mocker):
    create_mock = mocker.patch("app.dao.statistics_dao.__insert_job_stats", side_effect=IntegrityError("1", "2", "3"))
    update_mock = mocker.patch("app.dao.statistics_dao.__update_job_stats_sent_count", return_value=0)

    notification = sample_notification(notify_db, notify_db_session, job=sample_job)

    with pytest.raises(SQLAlchemyError) as e:
        create_or_update_job_sending_statistics(notification)
    assert 'Failed to create job statistics for {}'.format(sample_job.id) in str(e.value)

    update_mock.assert_has_calls([call(notification), call(notification)])
    create_mock.assert_called_once_with(notification)


@pytest.mark.parametrize('notification_type, sms_count, email_count, letter_count', [
    (SMS_TYPE, 1, 0, 0),
    (EMAIL_TYPE, 0, 1, 0),
    (LETTER_TYPE, 0, 0, 1)
])
def test_should_update_a_stats_entry_with_its_success_outcome_for_a_job(
        notify_db,
        notify_db_session,
        sample_job,
        sample_letter_template,
        notification_type,
        sms_count,
        email_count,
        letter_count
):
    template = None

    if notification_type == SMS_TYPE:
        template = sample_template(notify_db, notify_db_session, service=sample_job.service)

    if notification_type == EMAIL_TYPE:
        template = sample_email_template(notify_db, notify_db_session, service=sample_job.service)

    if notification_type == LETTER_TYPE:
        template = sample_letter_template

    notification = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_job.service,
        template=template,
        job=sample_job,
        status=NOTIFICATION_DELIVERED
    )

    create_or_update_job_sending_statistics(notification)

    stats = JobStatistics.query.all()

    assert len(stats) == 1

    update_job_stats_outcome_count(notification)

    stat = stats[0]
    assert stat.job_id == sample_job.id

    assert stat.emails_sent == email_count
    assert stat.sms_sent == sms_count
    assert stat.letters_sent == letter_count

    assert stat.emails_delivered == email_count
    assert stat.sms_delivered == sms_count

    assert stat.emails_failed == 0
    assert stat.sms_failed == 0
    assert stat.letters_failed == 0

    assert stat.sent == email_count + sms_count + letter_count
    assert stat.delivered == email_count + sms_count
    assert stat.failed == 0


@pytest.mark.parametrize('notification_type, sms_count, email_count, letter_count, status', [
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_TECHNICAL_FAILURE),
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_TEMPORARY_FAILURE),
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_PERMANENT_FAILURE),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_TECHNICAL_FAILURE),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_PERMANENT_FAILURE),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_TEMPORARY_FAILURE),
    (LETTER_TYPE, 0, 0, 1, NOTIFICATION_PERMANENT_FAILURE),
    (LETTER_TYPE, 0, 0, 1, NOTIFICATION_TEMPORARY_FAILURE),
    (LETTER_TYPE, 0, 0, 1, NOTIFICATION_TECHNICAL_FAILURE)
])
def test_should_update_a_stats_entry_with_its_error_outcomes_for_a_job(
        notify_db,
        notify_db_session,
        sample_job,
        sample_letter_template,
        notification_type,
        sms_count,
        email_count,
        letter_count,
        status
):
    template = None

    if notification_type == SMS_TYPE:
        template = sample_template(notify_db, notify_db_session, service=sample_job.service)

    if notification_type == EMAIL_TYPE:
        template = sample_email_template(notify_db, notify_db_session, service=sample_job.service)

    if notification_type == LETTER_TYPE:
        template = sample_letter_template

    notification = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_job.service,
        template=template,
        job=sample_job,
        status=status
    )

    create_or_update_job_sending_statistics(notification)

    stats = JobStatistics.query.all()

    assert len(stats) == 1

    update_job_stats_outcome_count(notification)

    stat = stats[0]
    assert stat.job_id == sample_job.id

    assert stat.emails_sent == email_count
    assert stat.sms_sent == sms_count
    assert stat.letters_sent == letter_count

    assert stat.emails_failed == email_count
    assert stat.letters_failed == letter_count
    assert stat.sms_failed == sms_count

    assert stat.emails_delivered == 0
    assert stat.sms_delivered == 0

    assert stat.sent == email_count + sms_count + letter_count
    assert stat.delivered == 0
    assert stat.failed == email_count + sms_count + letter_count


@pytest.mark.parametrize('notification_type, sms_count, email_count, letter_count, status', [
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_DELIVERED),
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_SENT),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_DELIVERED),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_SENT),
    (LETTER_TYPE, 0, 0, 1, NOTIFICATION_SENT),
    (LETTER_TYPE, 0, 0, 1, NOTIFICATION_DELIVERED),
])
def test_should_update_a_stats_entry_with_its_success_outcomes_for_a_job(
        notify_db,
        notify_db_session,
        sample_job,
        sample_letter_template,
        notification_type,
        sms_count,
        email_count,
        letter_count,
        status
):
    template = None

    if notification_type == SMS_TYPE:
        template = sample_template(notify_db, notify_db_session, service=sample_job.service)

    if notification_type == EMAIL_TYPE:
        template = sample_email_template(notify_db, notify_db_session, service=sample_job.service)

    if notification_type == LETTER_TYPE:
        template = sample_letter_template

    notification = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_job.service,
        template=template,
        job=sample_job,
        status=status
    )

    create_or_update_job_sending_statistics(notification)

    stats = JobStatistics.query.all()

    assert len(stats) == 1

    update_job_stats_outcome_count(notification)

    stat = stats[0]
    assert stat.job_id == sample_job.id

    assert stat.emails_sent == email_count
    assert stat.sms_sent == sms_count
    assert stat.letters_sent == letter_count

    assert stat.emails_failed == 0
    assert stat.letters_failed == 0
    assert stat.sms_failed == 0

    assert stat.emails_delivered == email_count
    assert stat.sms_delivered == sms_count

    assert stat.sent == email_count + sms_count + letter_count
    assert stat.delivered == 0 if notification_type == LETTER_TYPE else 1
    assert stat.failed == 0


@pytest.mark.parametrize('notification_type, sms_count, email_count, letter_count, status', [
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_PENDING),
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_CREATED),
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_FAILED),
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_SENDING),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_PENDING),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_CREATED),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_FAILED),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_SENDING),
    (LETTER_TYPE, 0, 0, 1, NOTIFICATION_PENDING),
    (LETTER_TYPE, 0, 0, 1, NOTIFICATION_CREATED),
    (LETTER_TYPE, 0, 0, 1, NOTIFICATION_FAILED),
    (LETTER_TYPE, 0, 0, 1, NOTIFICATION_SENDING)
])
def test_should_not_update_job_stats_if_irrelevant_status(
        notify_db,
        notify_db_session,
        sample_job,
        sample_letter_template,
        notification_type,
        sms_count,
        email_count,
        letter_count,
        status
):
    template = None

    if notification_type == SMS_TYPE:
        template = sample_template(notify_db, notify_db_session, service=sample_job.service)

    if notification_type == EMAIL_TYPE:
        template = sample_email_template(notify_db, notify_db_session, service=sample_job.service)

    if notification_type == LETTER_TYPE:
        template = sample_letter_template

    notification = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_job.service,
        template=template,
        job=sample_job,
        status=status
    )

    create_or_update_job_sending_statistics(notification)

    stats = JobStatistics.query.all()

    assert len(stats) == 1

    update_job_stats_outcome_count(notification)

    stat = stats[0]
    assert stat.job_id == sample_job.id

    assert stat.emails_sent == email_count
    assert stat.sms_sent == sms_count
    assert stat.letters_sent == letter_count

    assert stat.emails_failed == 0
    assert stat.letters_failed == 0
    assert stat.sms_failed == 0

    assert stat.emails_delivered == 0
    assert stat.sms_delivered == 0

    assert stat.sent == email_count + sms_count + letter_count
    assert stat.delivered == 0
    assert stat.failed == 0


@pytest.mark.parametrize('notification_type, sms_count, email_count, letter_count', [
    (SMS_TYPE, 2, 1, 1),
    (EMAIL_TYPE, 1, 2, 1),
    (LETTER_TYPE, 1, 1, 2)
])
def test_inserting_one_type_of_notification_maintains_other_counts(
        notify_db,
        notify_db_session,
        sample_job,
        sample_letter_template,
        notification_type,
        sms_count,
        email_count,
        letter_count
):
    sms_template = sample_template(notify_db, notify_db_session, service=sample_job.service)
    email_template = sample_email_template(notify_db, notify_db_session, service=sample_job.service)
    letter_template = sample_letter_template

    template = None

    if notification_type == SMS_TYPE:
        template = sms_template

    if notification_type == EMAIL_TYPE:
        template = email_template

    if notification_type == LETTER_TYPE:
        template = letter_template

    notification = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_job.service,
        template=template,
        job=sample_job,
        status=NOTIFICATION_CREATED
    )

    letter = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_job.service,
        template=letter_template,
        job=sample_job,
        status=NOTIFICATION_CREATED
    )

    email = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_job.service,
        template=email_template,
        job=sample_job,
        status=NOTIFICATION_CREATED
    )

    sms = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_job.service,
        template=sms_template,
        job=sample_job,
        status=NOTIFICATION_CREATED
    )

    create_or_update_job_sending_statistics(email)
    create_or_update_job_sending_statistics(sms)
    create_or_update_job_sending_statistics(letter)

    intitial_stats = JobStatistics.query.all()
    assert len(intitial_stats) == 1
    assert intitial_stats[0].emails_sent == 1
    assert intitial_stats[0].sms_sent == 1
    assert intitial_stats[0].letters_sent == 1

    create_or_update_job_sending_statistics(notification)

    updated_stats = JobStatistics.query.all()
    assert updated_stats[0].job_id == sample_job.id

    assert updated_stats[0].emails_sent == email_count
    assert updated_stats[0].sms_sent == sms_count
    assert updated_stats[0].letters_sent == letter_count

    if notification_type == EMAIL_TYPE:
        assert updated_stats[0].sent == email_count
    elif notification_type == SMS_TYPE:
        assert updated_stats[0].sent == sms_count
    elif notification_type == LETTER_TYPE:
        assert updated_stats[0].sent == letter_count


def test_updating_one_type_of_notification_to_success_maintains_other_counts(
        notify_db,
        notify_db_session,
        sample_service,
        sample_letter_template
):
    job_1 = sample_job(notify_db, notify_db_session, service=sample_service)
    job_2 = sample_job(notify_db, notify_db_session, service=sample_service)
    job_3 = sample_job(notify_db, notify_db_session, service=sample_service)

    sms_template = sample_template(notify_db, notify_db_session, service=sample_service)
    email_template = sample_email_template(notify_db, notify_db_session, service=sample_service)
    letter_template = sample_letter_template

    letter = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_service,
        template=letter_template,
        job=job_1,
        status=NOTIFICATION_CREATED
    )

    email = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_service,
        template=email_template,
        job=job_2,
        status=NOTIFICATION_CREATED
    )

    sms = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_service,
        template=sms_template,
        job=job_3,
        status=NOTIFICATION_CREATED
    )

    create_or_update_job_sending_statistics(email)
    create_or_update_job_sending_statistics(sms)
    create_or_update_job_sending_statistics(letter)

    sms.status = NOTIFICATION_DELIVERED
    email.status = NOTIFICATION_DELIVERED
    letter.status = NOTIFICATION_DELIVERED

    update_job_stats_outcome_count(letter)
    update_job_stats_outcome_count(email)
    update_job_stats_outcome_count(sms)

    stats = JobStatistics.query.order_by(JobStatistics.created_at).all()
    assert len(stats) == 3
    assert stats[0].letters_sent == 1
    assert stats[0].emails_sent == 0
    assert stats[0].sms_sent == 0
    assert stats[0].emails_delivered == 0
    assert stats[0].sms_delivered == 0

    assert stats[1].letters_sent == 0
    assert stats[1].emails_sent == 1
    assert stats[1].sms_sent == 0
    assert stats[1].emails_delivered == 1
    assert stats[1].sms_delivered == 0

    assert stats[2].letters_sent == 0
    assert stats[2].emails_sent == 0
    assert stats[2].sms_sent == 1
    assert stats[2].emails_delivered == 0
    assert stats[2].sms_delivered == 1

    assert stats[0].sent == 1
    assert stats[0].delivered == 0
    assert stats[0].failed == 0

    assert stats[1].sent == 1
    assert stats[1].delivered == 1
    assert stats[1].failed == 0

    assert stats[2].sent == 1
    assert stats[2].delivered == 1
    assert stats[2].failed == 0


def test_updating_one_type_of_notification_to_error_maintains_other_counts(
        notify_db,
        notify_db_session,
        sample_service,
        sample_letter_template
):
    job_1 = sample_job(notify_db, notify_db_session, service=sample_service)
    job_2 = sample_job(notify_db, notify_db_session, service=sample_service)
    job_3 = sample_job(notify_db, notify_db_session, service=sample_service)
    sms_template = sample_template(notify_db, notify_db_session, service=sample_service)
    email_template = sample_email_template(notify_db, notify_db_session, service=sample_service)
    letter_template = sample_letter_template

    letter = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_service,
        template=letter_template,
        job=job_1,
        status=NOTIFICATION_CREATED
    )

    email = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_service,
        template=email_template,
        job=job_2,
        status=NOTIFICATION_CREATED
    )

    sms = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_service,
        template=sms_template,
        job=job_3,
        status=NOTIFICATION_CREATED
    )

    create_or_update_job_sending_statistics(email)
    create_or_update_job_sending_statistics(sms)
    create_or_update_job_sending_statistics(letter)

    sms.status = NOTIFICATION_TECHNICAL_FAILURE
    email.status = NOTIFICATION_TECHNICAL_FAILURE
    letter.status = NOTIFICATION_TECHNICAL_FAILURE

    update_job_stats_outcome_count(letter)
    update_job_stats_outcome_count(email)
    update_job_stats_outcome_count(sms)

    stats = JobStatistics.query.order_by(JobStatistics.created_at).all()
    assert len(stats) == 3
    assert stats[0].emails_sent == 0
    assert stats[0].sms_sent == 0
    assert stats[0].letters_sent == 1
    assert stats[0].emails_delivered == 0
    assert stats[0].sms_delivered == 0
    assert stats[0].sms_failed == 0
    assert stats[0].emails_failed == 0
    assert stats[0].letters_failed == 1

    assert stats[1].emails_sent == 1
    assert stats[1].sms_sent == 0
    assert stats[1].letters_sent == 0
    assert stats[1].emails_delivered == 0
    assert stats[1].sms_delivered == 0
    assert stats[1].sms_failed == 0
    assert stats[1].emails_failed == 1
    assert stats[1].letters_failed == 0

    assert stats[2].emails_sent == 0
    assert stats[2].sms_sent == 1
    assert stats[2].letters_sent == 0
    assert stats[2].emails_delivered == 0
    assert stats[2].sms_delivered == 0
    assert stats[2].sms_failed == 1
    assert stats[2].emails_failed == 0
    assert stats[1].letters_failed == 0

    assert stats[0].sent == 1
    assert stats[0].delivered == 0
    assert stats[0].failed == 1

    assert stats[1].sent == 1
    assert stats[1].delivered == 0
    assert stats[1].failed == 1

    assert stats[2].sent == 1
    assert stats[2].delivered == 0
    assert stats[2].failed == 1


def test_will_not_timeout_job_counts_before_notification_timeouts(notify_db, notify_db_session,
                                                                  sample_job, sample_template):

    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)

    sms = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_job.service,
        template=sample_template,
        job=sample_job,
        status=NOTIFICATION_CREATED
    )

    sms_2 = sample_notification(
        notify_db,
        notify_db_session,
        service=sample_job.service,
        template=sample_template,
        job=sample_job,
        status=NOTIFICATION_CREATED
    )

    create_or_update_job_sending_statistics(sms)
    create_or_update_job_sending_statistics(sms_2)

    JobStatistics.query.update({JobStatistics.created_at: one_minute_ago})

    initial_stats = JobStatistics.query.all()

    assert initial_stats[0].emails_sent == 0
    assert initial_stats[0].sms_sent == 2
    assert initial_stats[0].emails_delivered == 0
    assert initial_stats[0].sms_delivered == 0
    assert initial_stats[0].sms_failed == 0
    assert initial_stats[0].emails_failed == 0

    assert initial_stats[0].sent == 2
    assert initial_stats[0].delivered == 0
    assert initial_stats[0].failed == 0

    dao_timeout_job_statistics(61)
    updated_stats = JobStatistics.query.all()
    assert updated_stats[0].emails_sent == 0
    assert updated_stats[0].sms_sent == 2
    assert updated_stats[0].emails_delivered == 0
    assert updated_stats[0].sms_delivered == 0
    assert updated_stats[0].sms_failed == 0
    assert updated_stats[0].emails_failed == 0

    assert initial_stats[0].sent == 2
    assert initial_stats[0].delivered == 0
    assert initial_stats[0].failed == 0


@pytest.mark.parametrize('notification_type, sms_count, email_count', [
    (SMS_TYPE, 3, 0),
    (EMAIL_TYPE, 0, 3),
])
def test_timeout_job_counts_timesout_multiple_jobs(
        notify_db, notify_db_session, notification_type, sms_count, email_count
):
    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)

    job_1 = sample_job(notify_db, notify_db_session)
    job_2 = sample_job(notify_db, notify_db_session)
    job_3 = sample_job(notify_db, notify_db_session)

    jobs = [job_1, job_2, job_3]

    for job in jobs:
        if notification_type == EMAIL_TYPE:
            template = sample_email_template(notify_db, notify_db_session, service=job.service)
        else:
            template = sample_template(notify_db, notify_db_session, service=job.service)

        for i in range(3):
            n = sample_notification(
                notify_db,
                notify_db_session,
                service=job.service,
                template=template,
                job=job,
                status=NOTIFICATION_CREATED
            )
            create_or_update_job_sending_statistics(n)

    JobStatistics.query.update({JobStatistics.created_at: one_minute_ago})
    initial_stats = JobStatistics.query.all()
    for stats in initial_stats:
        assert stats.emails_sent == email_count
        assert stats.sms_sent == sms_count
        assert stats.emails_delivered == 0
        assert stats.sms_delivered == 0
        assert stats.sms_failed == 0
        assert stats.emails_failed == 0
        assert stats.sent == email_count + sms_count
        assert stats.delivered == 0
        assert stats.failed == 0

    dao_timeout_job_statistics(1)
    updated_stats = JobStatistics.query.all()
    for stats in updated_stats:
        assert stats.emails_sent == email_count
        assert stats.sms_sent == sms_count
        assert stats.emails_delivered == 0
        assert stats.sms_delivered == 0
        assert stats.sms_failed == sms_count
        assert stats.emails_failed == email_count
        assert stats.sent == email_count + sms_count
        assert stats.delivered == 0
        assert stats.failed == email_count + sms_count


count_notifications = len(NOTIFICATION_STATUS_TYPES)
count_success_notifications = len(NOTIFICATION_STATUS_SUCCESS)
count_error_notifications = len(NOTIFICATION_STATUS_TYPES) - len(NOTIFICATION_STATUS_SUCCESS)


def test_timeout_job_sets_all_non_delivered_emails_to_error_and_doesnt_affect_sms(
        notify_db,
        notify_db_session
):
    service = sample_service(notify_db, notify_db_session)

    sms_template = sample_template(notify_db, notify_db_session, service=service)
    email_template = sample_email_template(notify_db, notify_db_session, service=service)

    email_job = sample_job(
        notify_db, notify_db_session, template=email_template, service=service
    )
    sms_job = sample_job(
        notify_db, notify_db_session, template=sms_template, service=service
    )

    # Make an email notification in every state
    for i in range(len(NOTIFICATION_STATUS_TYPES)):
        n = sample_notification(
            notify_db,
            notify_db_session,
            service=email_job.service,
            template=email_template,
            job=email_job,
            status=NOTIFICATION_STATUS_TYPES[i]
        )
        create_or_update_job_sending_statistics(n)

    # single sms notification
    sms_notification = sample_notification(
        notify_db, notify_db_session, service=service, template=sms_template, job=sms_job
    )
    create_or_update_job_sending_statistics(sms_notification)

    # fudge the created at time on the job stats table to make the eligible for timeout query
    JobStatistics.query.update({
        JobStatistics.created_at: datetime.utcnow() - timedelta(minutes=1)
    })

    # should have sent an email for every state (len(NOTIFICATION_STATUS_TYPES))
    initial_stats = JobStatistics.query.filter_by(job_id=email_job.id).all()
    assert len(initial_stats) == 1
    assert initial_stats[0].emails_sent == count_notifications
    assert initial_stats[0].sms_sent == 0
    assert initial_stats[0].emails_delivered == 0
    assert initial_stats[0].sms_delivered == 0
    assert initial_stats[0].sms_failed == 0
    assert initial_stats[0].emails_failed == 0

    assert initial_stats[0].sent == count_notifications
    assert initial_stats[0].delivered == 0
    assert initial_stats[0].failed == 0

    # timeout the notifications
    dao_timeout_job_statistics(1)

    # after timeout all delivered states are success and ALL other states are failed
    updated_stats = JobStatistics.query.filter_by(job_id=email_job.id).all()
    assert updated_stats[0].emails_sent == count_notifications
    assert updated_stats[0].sms_sent == 0
    assert updated_stats[0].emails_delivered == count_success_notifications
    assert updated_stats[0].sms_delivered == 0
    assert updated_stats[0].sms_failed == 0
    assert updated_stats[0].emails_failed == count_error_notifications

    assert initial_stats[0].sent == count_notifications
    assert initial_stats[0].delivered == count_success_notifications
    assert initial_stats[0].failed == count_error_notifications

    sms_stats = JobStatistics.query.filter_by(job_id=sms_job.id).all()
    assert sms_stats[0].emails_sent == 0
    assert sms_stats[0].sms_sent == 1
    assert sms_stats[0].emails_delivered == 0
    assert sms_stats[0].sms_delivered == 0
    assert sms_stats[0].sms_failed == 1
    assert sms_stats[0].emails_failed == 0
    assert sms_stats[0].sent == 1
    assert sms_stats[0].delivered == 0
    assert sms_stats[0].failed == 1


# this test is as above, but for SMS not email
def test_timeout_job_sets_all_non_delivered_states_to_error(
        notify_db,
        notify_db_session,
        sample_job
):
    for i in range(len(NOTIFICATION_STATUS_TYPES)):
        n = sample_notification(
            notify_db,
            notify_db_session,
            service=sample_job.service,
            template=sample_template(notify_db, notify_db_session, service=sample_job.service),
            job=sample_job,
            status=NOTIFICATION_STATUS_TYPES[i]
        )
        create_or_update_job_sending_statistics(n)

    JobStatistics.query.update({JobStatistics.created_at: datetime.utcnow() - timedelta(minutes=1)})
    initial_stats = JobStatistics.query.all()
    for stats in initial_stats:
        assert stats.emails_sent == 0
        assert stats.sms_sent == count_notifications
        assert stats.emails_delivered == 0
        assert stats.sms_delivered == 0
        assert stats.sms_failed == 0
        assert stats.emails_failed == 0

        assert stats.sent == count_notifications
        assert stats.delivered == 0
        assert stats.failed == 0

    dao_timeout_job_statistics(1)
    updated_stats = JobStatistics.query.all()

    for stats in updated_stats:
        assert stats.emails_sent == 0
        assert stats.sms_sent == count_notifications
        assert stats.emails_delivered == 0
        assert stats.sms_delivered == count_success_notifications
        assert stats.sms_failed == count_error_notifications
        assert stats.emails_failed == 0

        assert stats.sent == count_notifications
        assert stats.delivered == count_success_notifications
        assert stats.failed == count_error_notifications
