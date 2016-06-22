from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app import notify_celery
from app.clients import STATISTICS_FAILURE
from app.dao.invited_user_dao import delete_invitations_created_more_than_two_days_ago
from app.dao.notifications_dao import delete_notifications_created_more_than_a_week_ago, get_notifications, \
    update_notification_status_by_id
from app.dao.users_dao import delete_codes_older_created_more_than_a_day_ago


@notify_celery.task(name="delete-verify-codes")
def delete_verify_codes():
    try:
        start = datetime.utcnow()
        deleted = delete_codes_older_created_more_than_a_day_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} verify codes".format(start, datetime.utcnow(), deleted)
        )
    except SQLAlchemyError:
        current_app.logger.info("Failed to delete verify codes")
        raise


@notify_celery.task(name="delete-successful-notifications")
def delete_successful_notifications():
    try:
        start = datetime.utcnow()
        deleted = delete_notifications_created_more_than_a_week_ago('delivered')
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} successful notifications".format(
                start,
                datetime.utcnow(),
                deleted
            )
        )
    except SQLAlchemyError:
        current_app.logger.info("Failed to delete successful notifications")
        raise


@notify_celery.task(name="delete-failed-notifications")
def delete_failed_notifications():
    try:
        start = datetime.utcnow()
        deleted = delete_notifications_created_more_than_a_week_ago('failed')
        deleted += delete_notifications_created_more_than_a_week_ago('technical-failure')
        deleted += delete_notifications_created_more_than_a_week_ago('temporary-failure')
        deleted += delete_notifications_created_more_than_a_week_ago('permanent-failure')
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} failed notifications".format(
                start,
                datetime.utcnow(),
                deleted
            )
        )
    except SQLAlchemyError:
        current_app.logger.info("Failed to delete failed notifications")
        raise


@notify_celery.task(name="delete-invitations")
def delete_invitations():
    try:
        start = datetime.utcnow()
        deleted = delete_invitations_created_more_than_two_days_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} invitations".format(start, datetime.utcnow(), deleted)
        )
    except SQLAlchemyError:
        current_app.logger.info("Failed to delete invitations")
        raise


@notify_celery.task(name='timeout-sending-notifications')
def timeout_notifications():
    notifications = get_notifications(filter_dict={'status': 'sending'})
    now = datetime.utcnow()
    for noti in notifications:
        try:
            if (now - noti.created_at) > timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD')
            ):
                update_notification_status_by_id(noti.id, 'temporary-failure', STATISTICS_FAILURE)
                current_app.logger.info((
                    "Timeout period reached for notification ({})"
                    ", status has been updated.").format(noti.id))
        except Exception as e:
            current_app.logger.exception(e)
            current_app.logger.error((
                "Exception raised trying to timeout notification ({})"
                ", skipping notification update.").format(noti.id))
