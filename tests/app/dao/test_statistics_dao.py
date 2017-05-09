from unittest.mock import call

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.dao.statistics_dao import (
    create_or_update_job_sending_statistics,
    update_job_stats_outcome_count
)
from app.models import (
    JobStatistics,
    SMS_TYPE,
    EMAIL_TYPE,
    LETTER_TYPE,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_PENDING, NOTIFICATION_CREATED, NOTIFICATION_FAILED, NOTIFICATION_SENT, NOTIFICATION_SENDING)
from tests.app.conftest import sample_notification, sample_email_template, sample_template


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
    assert not len(JobStatistics.query.all())

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
    assert not len(JobStatistics.query.all())

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
    assert not len(JobStatistics.query.all())

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
    assert not len(JobStatistics.query.all())

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


@pytest.mark.parametrize('notification_type, sms_count, email_count, letter_count, status', [
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_PENDING),
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_CREATED),
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_FAILED),
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_SENT),
    (SMS_TYPE, 1, 0, 0, NOTIFICATION_SENDING),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_PENDING),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_CREATED),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_FAILED),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_SENT),
    (EMAIL_TYPE, 0, 1, 0, NOTIFICATION_SENDING),
    (LETTER_TYPE, 0, 0, 1, NOTIFICATION_PENDING),
    (LETTER_TYPE, 0, 0, 1, NOTIFICATION_CREATED),
    (LETTER_TYPE, 0, 0, 1, NOTIFICATION_FAILED),
    (LETTER_TYPE, 0, 0, 1, NOTIFICATION_SENT),
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
    assert not len(JobStatistics.query.all())

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
