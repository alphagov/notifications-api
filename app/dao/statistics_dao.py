from flask import current_app

from app import db
from app.dao.dao_utils import transactional
from app.models import NotificationStatistics, TemplateStatistics, JobStatistics
from app.statsd_decorators import statsd
from sqlalchemy.exc import SQLAlchemyError


@statsd(namespace="dao")
@transactional
def save_notification_statistics(notification):
    if update_notification_stats(notification) == 0:
        try:
            insert_notification_stats(notification)
        except SQLAlchemyError as e:
            current_app.logger.exception(e)
            update_notification_stats(notification)


def insert_notification_stats(notification):
    stats = NotificationStatistics(
        day=notification.created_at.strftime('%Y-%m-%d'),
        service_id=notification.service_id,
        sms_requested=1,
        sms_billable_units=(notification.billable_units * notification.rate_multiplier),
        emails_requested=0
    )
    db.session.add(stats)


def update_notification_stats(notification):
    update = {
        NotificationStatistics.sms_requested: NotificationStatistics.sms_requested + 1,
        NotificationStatistics.sms_billable_units: NotificationStatistics.sms_billable_units + (notification.billable_units * notification.rate_multiplier)

    }
    return db.session.query(NotificationStatistics).filter_by(
        day=notification.created_at.strftime('%Y-%m-%d'),
        service_id=notification.service_id
    ).update(update)


@statsd(namespace="dao")
@transactional
def save_template_statistics(notification):
    if update_template_stats(notification) == 0:
        try:
            insert_template_stats(notification)
        except SQLAlchemyError as e:
            current_app.logger.exception(e)
            update_template_stats(notification)


def insert_template_stats(notification):
    stats = TemplateStatistics(
        day=notification.created_at.strftime('%Y-%m-%d'),
        service_id=notification.service_id,
        template_id=notification.template_id,
        usage_count=1
    )
    db.session.add(stats)


def update_template_stats(notification):
    update = {
        TemplateStatistics.usage_count: TemplateStatistics.usage_count + 1
    }

    return db.session.query(TemplateStatistics).filter_by(
        day=notification.created_at.strftime('%Y-%m-%d'),
        service_id=notification.service_id
    ).update(update)


@statsd(namespace="dao")
@transactional
def save_job_statistics(notification):
    if update_job_stats(notification) == 0:
        try:
            insert_job_stats(notification)
        except SQLAlchemyError as e:
            current_app.logger.exception(e)
            update_template_stats(notification)


def insert_job_stats(notification):
    stats = JobStatistics(
        job_id=notification.job_id,
        sms_requested=1
    )
    db.session.add(stats)


def update_job_stats(notification):
    update = {
        JobStatistics.sms_requested: JobStatistics.sms_requested + 1
    }

    return db.session.query(JobStatistics).filter_by(
        job_id=notification.job_id
    ).update(update)
