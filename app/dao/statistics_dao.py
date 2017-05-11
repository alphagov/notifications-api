from datetime import datetime, timedelta

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
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENT)
from app.statsd_decorators import statsd


@transactional
def timeout_job_counts(notifications_type, timeout_start):
    sent = columns(notifications_type, 'sent')
    delivered = columns(notifications_type, 'delivered')
    failed = columns(notifications_type, 'failed')

    query = JobStatistics.query.filter(
        JobStatistics.created_at < timeout_start,
        sent != failed + delivered
    )
    return query.update(
        {failed: sent - delivered}, synchronize_session=False
    )


@statsd(namespace="dao")
def timeout_job_statistics(timeout_period):
    timeout_start = datetime.utcnow() - timedelta(seconds=timeout_period)
    sms_count = timeout_job_counts(SMS_TYPE, timeout_start)
    email_count = timeout_job_counts(EMAIL_TYPE, timeout_start)
    return sms_count + email_count


@statsd(namespace="dao")
def create_or_update_job_sending_statistics(notification):
    if __update_job_stats_sent_count(notification) == 0:
        try:
            __insert_job_stats(notification)
        except IntegrityError as e:
            current_app.logger.exception(e)
            if __update_job_stats_sent_count(notification) == 0:
                raise SQLAlchemyError("Failed to create job statistics for {}".format(notification.job_id))


@transactional
def __update_job_stats_sent_count(notification):
    column = columns(notification.notification_type, 'sent')

    return db.session.query(JobStatistics).filter_by(
        job_id=notification.job_id,
    ).update({
        column: column + 1
    })


@transactional
def __insert_job_stats(notification):
    stats = JobStatistics(
        job_id=notification.job_id,
        emails_sent=1 if notification.notification_type == EMAIL_TYPE else 0,
        sms_sent=1 if notification.notification_type == SMS_TYPE else 0,
        letters_sent=1 if notification.notification_type == LETTER_TYPE else 0,
        updated_at=datetime.utcnow()
    )
    db.session.add(stats)


def columns(notification_type, status):
    keys = {
        EMAIL_TYPE: {
            'failed': JobStatistics.emails_failed,
            'delivered': JobStatistics.emails_delivered,
            'sent': JobStatistics.emails_sent
        },
        SMS_TYPE: {
            'failed': JobStatistics.sms_failed,
            'delivered': JobStatistics.sms_delivered,
            'sent': JobStatistics.sms_sent
        },
        LETTER_TYPE: {
            'failed': JobStatistics.letters_failed,
            'sent': JobStatistics.letters_sent
        }
    }
    return keys.get(notification_type).get(status)


@transactional
def update_job_stats_outcome_count(notification):
    if notification.status in NOTIFICATION_STATUS_TYPES_FAILED:
        column = columns(notification.notification_type, 'failed')

    elif notification.status in [NOTIFICATION_DELIVERED,
                                 NOTIFICATION_SENT] and notification.notification_type != LETTER_TYPE:
        column = columns(notification.notification_type, 'delivered')

    else:
        column = None

    if column:
        return db.session.query(JobStatistics).filter_by(
            job_id=notification.job_id,
        ).update({
            column: column + 1
        })
    else:
        return 0
