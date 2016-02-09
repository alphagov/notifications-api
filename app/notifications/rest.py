import uuid

from flask import (
    Blueprint,
    jsonify,
    request
)

from app import api_user
from app.aws_sqs import add_notification_to_queue
from app.dao import (templates_dao)
from app.schemas import (
    email_notification_schema, sms_template_notification_schema)

notifications = Blueprint('notifications', __name__)


@notifications.route('/<notification_id>', methods=['GET'])
def get_notifications(notification_id):
    # TODO return notification id details
    return jsonify({'id': notification_id}), 200


@notifications.route('/sms', methods=['POST'])
def create_sms_notification():
    resp_json = request.get_json()

    notification, errors = sms_template_notification_schema.load(resp_json)
    if errors:
        return jsonify(result="error", message=errors), 400

    add_notification_to_queue(api_user['client'], notification['template'], 'sms', notification)
    # TODO data to be returned
    return jsonify({}), 204


@notifications.route('/email', methods=['POST'])
def create_email_notification():
    resp_json = request.get_json()
    notification, errors = email_notification_schema.load(resp_json)
    if errors:
        return jsonify(result="error", message=errors), 400
    add_notification_to_queue(api_user['client'], "admin", 'email', notification)
    # TODO data to be returned
    return jsonify({}), 204


@notifications.route('/sms/service/<service_id>', methods=['POST'])
def create_sms_for_service(service_id):

    resp_json = request.get_json()

    notification, errors = sms_template_notification_schema.load(resp_json)
    if errors:
        return jsonify(result="error", message=errors), 400

    template_id = notification['template']
    job_id = notification['job']

    # TODO: job/job_id is in notification and can used to update job status

    # TODO: remove once beta is reading notifications from the queue
    template = templates_dao.get_model_templates(template_id)

    if template.service.id != uuid.UUID(service_id):
        message = "Invalid template: id {} for service id: {}".format(template.id, service_id)
        return jsonify(result="error", message=message), 400

    add_notification_to_queue(service_id, template_id, 'sms', notification)
    # TODO data to be returned
    return jsonify({}), 204
