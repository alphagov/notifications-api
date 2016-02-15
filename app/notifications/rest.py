import uuid

from flask import (
    Blueprint,
    jsonify,
    request,
    current_app)
from itsdangerous import URLSafeSerializer

from app import api_user
from app.aws_sqs import add_notification_to_queue
from app.dao import (templates_dao)
from app.schemas import (
    email_notification_schema, sms_template_notification_schema)
from app.celery.tasks import send_sms


notifications = Blueprint('notifications', __name__)


def create_notification_id():
    return str(uuid.uuid4())


@notifications.route('/<notification_id>', methods=['GET'])
def get_notifications(notification_id):
    # TODO return notification id details
    return jsonify({'id': notification_id}), 200


@notifications.route('/sms', methods=['POST'])
def create_sms_notification():
    serializer = URLSafeSerializer(current_app.config.get('SECRET_KEY'))

    resp_json = request.get_json()

    notification, errors = sms_template_notification_schema.load(resp_json)
    if errors:
        return jsonify(result="error", message=errors), 400

    notification_id = create_notification_id()
    encrypted_notification = serializer.dumps(notification, current_app.config.get('DANGEROUS_SALT'))

    send_sms.apply_async((
        api_user['client'],
        notification_id,
        encrypted_notification,
        current_app.config.get('SECRET_KEY'),
        current_app.config.get('DANGEROUS_SALT')))
    return jsonify({'notification_id': notification_id}), 201


@notifications.route('/email', methods=['POST'])
def create_email_notification():
    resp_json = request.get_json()
    notification, errors = email_notification_schema.load(resp_json)
    if errors:
        return jsonify(result="error", message=errors), 400
    notification_id = add_notification_to_queue(api_user['client'], "admin", 'email', notification)
    return jsonify({'notification_id': notification_id}), 201


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

    notification_id = add_notification_to_queue(service_id, template_id, 'sms', notification)
    return jsonify({'notification_id': notification_id}), 201
