import uuid

from flask import (
    Blueprint,
    jsonify,
    request,
    current_app
)

from app import api_user, encryption
from app.dao import (
    templates_dao,
    services_dao,
    notifications_dao,
    jobs_dao
)
from app.schemas import (
    email_notification_schema,
    sms_template_notification_schema,
    notification_status_schema,
    job_sms_template_notification_schema
)
from app.celery.tasks import send_sms, send_email
from sqlalchemy.orm.exc import NoResultFound

notifications = Blueprint('notifications', __name__)

from app.errors import register_errors

register_errors(notifications)


def create_notification_id():
    return str(uuid.uuid4())


@notifications.route('/<string:notification_id>', methods=['GET'])
def get_notifications(notification_id):
    try:
        notification = notifications_dao.get_notification(api_user['client'], notification_id)
        return jsonify({'notification': notification_status_schema.dump(notification).data}), 200
    except NoResultFound:
        return jsonify(result="error", message="not found"), 404


@notifications.route('/sms', methods=['POST'])
def create_sms_notification():
    notification, errors = sms_template_notification_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400

    template = templates_dao.dao_get_template_by_id_and_service_id(
        template_id=notification['template'],
        service_id=api_user['client']
    )

    if not template:
        return jsonify(result="error", message={'template': ['Template not found']}), 400

    service = services_dao.dao_fetch_service_by_id(api_user['client'])

    if service.restricted:
        if notification['to'] not in [user.email_address for user in service.users]:
            return jsonify(result="error", message={'to': ['Invalid phone number for restricted service']}), 400

    notification_id = create_notification_id()

    send_sms.apply_async((
        api_user['client'],
        notification_id,
        encryption.encrypt(notification)),
        queue='sms')
    return jsonify({'notification_id': notification_id}), 201


@notifications.route('/sms/service/<service_id>', methods=['POST'])
def create_sms_for_service(service_id):
    notification, errors = job_sms_template_notification_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400

    template = templates_dao.dao_get_template_by_id_and_service_id(
        template_id=notification['template'],
        service_id=service_id
    )

    if not template:
        return jsonify(result="error", message={'template': ['Template or service not found']}), 400

    job_id = notification['job']

    job = jobs_dao.get_job(service_id, job_id)

    if not job:
        return jsonify(result="error", message={'job': ['Job not found']}), 400

    service = services_dao.dao_fetch_service_by_id(service_id)

    if service.restricted:
        if notification['to'] not in [user.email_address for user in service.users]:
            return jsonify(result="error", message={'to': ['Invalid phone number for restricted service']}), 400

    notification_id = create_notification_id()

    send_sms.apply_async((
        api_user['client'],
        notification_id,
        encryption.encrypt(notification),
        job_id),
        queue='sms')
    return jsonify({'notification_id': notification_id}), 201


@notifications.route('/email', methods=['POST'])
def create_email_notification():
    notification, errors = email_notification_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400

    template = templates_dao.dao_get_template_by_id_and_service_id(
        template_id=notification['template'],
        service_id=api_user['client']
    )

    if not template:
        return jsonify(result="error", message={'template': ['Template not found']}), 400

    service = services_dao.dao_fetch_service_by_id(api_user['client'])

    if service.restricted:
        if notification['to'] not in [user.email_address for user in service.users]:
            return jsonify(result="error", message={'to': ['Email address not permitted for restricted service']}), 400

    notification_id = create_notification_id()

    send_email.apply_async((
        api_user['client'],
        notification_id,
        template.subject,
        "{}@{}".format(service.email_from, current_app.config['NOTIFY_EMAIL_DOMAIN']),
        encryption.encrypt(notification)),
        queue='email')
    return jsonify({'notification_id': notification_id}), 201
