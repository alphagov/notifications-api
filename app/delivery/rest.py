from flask import Blueprint, jsonify

from app.config import QueueNames
from app.delivery import send_to_providers
from app.models import EMAIL_TYPE
from app.celery import provider_tasks
from app.dao import notifications_dao
from flask import current_app

delivery_blueprint = Blueprint('delivery', __name__)

from app.errors import register_errors

register_errors(delivery_blueprint)


@delivery_blueprint.route('/deliver/notification/<uuid:notification_id>', methods=['POST'])
def send_notification_to_provider(notification_id):
    notification = notifications_dao.get_notification_by_id(notification_id)
    if not notification:
        return jsonify({"result": "error", "message": "No result found"}), 404

    if notification.notification_type == EMAIL_TYPE:
        send_response(
            send_to_providers.send_email_to_provider,
            provider_tasks.deliver_email,
            notification)
    else:
        send_response(
            send_to_providers.send_sms_to_provider,
            provider_tasks.deliver_sms,
            notification)
    return jsonify({}), 204


def send_response(send_call, task_call, notification):
    try:
        send_call(notification)
    except Exception as e:
        current_app.logger.exception(
            "Failed to send notification, retrying in celery. ID {} type {}".format(
                notification.id,
                notification.notification_type),
            e)
        task_call.apply_async((str(notification.id)), queue=QueueNames.SEND)
