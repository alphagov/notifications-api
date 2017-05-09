from flask import current_app
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import db
from app.dao.dao_utils import transactional
from app.models import (
    JobStatistics,
    EMAIL_TYPE,
    SMS_TYPE,
    LETTER_TYPE,
    NOTIFICATION_STATUS_TYPES_FAILED,
    NOTIFICATION_DELIVERED
)
from app.statsd_decorators import statsd


@statsd(namespace="dao")
def create_or_update_job_sending_statistics(notification):
    if __update_job_stats_sent_count(notification) == 0:
        try:
            __insert_job_stats(notification)
        except IntegrityError as e:
            current_app.logger.exception(e)
            if __update_job_stats_sent_count(notification) == 0:
                raise SQLAlchemyError("Failed to create job statistics for {}".format(notification.job_id))


def __update_job_stats_sent_count(notification):
    update = {
        JobStatistics.emails_sent:
            JobStatistics.emails_sent + 1 if notification.notification_type == EMAIL_TYPE else 0,
        JobStatistics.sms_sent:
            JobStatistics.sms_sent + 1 if notification.notification_type == SMS_TYPE else 0,
        JobStatistics.letters_sent:
            JobStatistics.letters_sent + 1 if notification.notification_type == LETTER_TYPE else 0
    }
    return db.session.query(JobStatistics).filter_by(
        job_id=notification.job_id,
    ).update(update)


@transactional
def __insert_job_stats(notification):

    stats = JobStatistics(
        job_id=notification.job_id,
        emails_sent=1 if notification.notification_type == EMAIL_TYPE else 0,
        sms_sent=1 if notification.notification_type == SMS_TYPE else 0,
        letters_sent=1 if notification.notification_type == LETTER_TYPE else 0
    )
    db.session.add(stats)


def update_job_stats_outcome_count(notification):
    update = None

    if notification.status in NOTIFICATION_STATUS_TYPES_FAILED:
        update = {
            JobStatistics.emails_failed:
                JobStatistics.emails_failed + 1 if notification.notification_type == EMAIL_TYPE else 0,
            JobStatistics.sms_failed:
                JobStatistics.sms_failed + 1 if notification.notification_type == SMS_TYPE else 0,
            JobStatistics.letters_failed:
                JobStatistics.letters_failed + 1 if notification.notification_type == LETTER_TYPE else 0
        }

    elif notification.status == NOTIFICATION_DELIVERED and notification.notification_type != LETTER_TYPE:
        update = {
            JobStatistics.emails_delivered:
                JobStatistics.emails_delivered + 1 if notification.notification_type == EMAIL_TYPE else 0,
            JobStatistics.sms_delivered:
                JobStatistics.sms_delivered + 1 if notification.notification_type == SMS_TYPE else 0
        }

    if update:
        return db.session.query(JobStatistics).filter_by(
            job_id=notification.job_id,
        ).update(update)
    else:
        return 0
