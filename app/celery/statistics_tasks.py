from flask import current_app

from app import notify_celery
from app.dao.notifications_dao import get_notification_by_id
from app.dao.statistics_dao import save_notification_statistics, save_template_statistics
from app.statsd_decorators import statsd


@notify_celery.task(bind=True, name='update-notification-statistics')
@statsd(namespace="tasks")
def update_notification_statistics(self, notification_id):
    notification = get_notification_by_id(notification_id)

    save_notification_statistics(notification)

    current_app.logger.info("Updated {} notification statistics".format(notification_id))
