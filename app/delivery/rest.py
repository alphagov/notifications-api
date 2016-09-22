from flask import Blueprint, jsonify

from app.delivery import send_to_providers
from app.models import EMAIL_TYPE
from app.celery import provider_tasks
from app.dao import notifications_dao

delivery = Blueprint('delivery', __name__)

from app.errors import register_errors

register_errors(delivery)


@delivery.route('/deliver/notification/<uuid:notification_id>',  methods=['POST'])
def send_notification_to_provider(notification_id):

    notification = notifications_dao.get_notification_by_id(notification_id)
    if not notification:
        return jsonify(notification={"result": "error", "message": "No result found"}), 404

    if notification.notification_type == EMAIL_TYPE:
        send_response(send_to_providers.send_email_response, provider_tasks.deliver_email, notification_id, 'send-email')
    else:
        send_response(send_to_providers.send_sms_response, provider_tasks.deliver_sms, notification_id, 'send-sms')
    return jsonify({}), 204


def send_response(send_call, task_call, notification, queue):
    try:
        send_call(notification)
    except Exception as e:
        task_call.apply_async((str(notification.id)), queue=queue)
