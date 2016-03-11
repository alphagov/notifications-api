from datetime import datetime
import uuid

from flask import (
    Blueprint,
    jsonify,
    request,
    current_app,
    url_for,
    json
)

from utils.template import Template
from app.clients.sms.firetext import firetext_response_status
from app.clients.email.aws_ses import ses_response_status
from app import api_user, encryption, create_uuid, DATETIME_FORMAT, DATE_FORMAT
from app.authentication.auth import require_admin
from app.dao import (
    templates_dao,
    services_dao,
    notifications_dao
)
from app.schemas import (
    email_notification_schema,
    sms_template_notification_schema,
    notification_status_schema
)
from app.celery.tasks import send_sms, send_email
from sqlalchemy.orm.exc import NoResultFound

notifications = Blueprint('notifications', __name__)

from app.errors import register_errors

register_errors(notifications)


@notifications.route('/notifications/email/ses', methods=['POST'])
def process_ses_response():
    try:
        ses_request = json.loads(request.data)

        if 'Message' not in ses_request:
            current_app.logger.error(
                "SES callback failed: message missing"
            )
            return jsonify(
                result="error", message="SES callback failed: message missing"
            ), 400

        if 'notificationType' not in ses_request['Message']:
            current_app.logger.error(
                "SES callback failed: notificationType missing"
            )
            return jsonify(
                result="error", message="SES callback failed: notificationType missing"
            ), 400

        status = ses_response_status.get(ses_request['Message']['notificationType'], None)
        if not status:
            current_app.logger.info(
                "SES callback failed: status {} not found.".format(status)
            )
            return jsonify(
                result="error",
                message="SES callback failed: status {} not found".format(ses_request['Message']['notificationType'])
            ), 400

        try:
            recipients = ses_request['Message']['mail']['destination']

            if notifications_dao.update_notification_status_by_to(recipients[0], status['notify_status']) == 0:
                current_app.logger.info(
                    "SES callback failed: notification not found. Status {}".format(status['notify_status'])
                )
                return jsonify(
                    result="error",
                    message="SES callback failed: notification not found. Status {}".format(status['notify_status'])
                ), 404
            return jsonify(
                result="success", message="SES callback succeeded"
            ), 200

        except KeyError:
            current_app.logger.error(
                "SES callback failed: destination missing"
            )
            return jsonify(
                result="error", message="SES callback failed: destination missing"
            ), 400

    except ValueError as ex:
        current_app.logger.exception(
            "SES callback failed: invalid json {}".format(ex)
        )
        return jsonify(
            result="error", message="SES callback failed: invalid json"
        ), 400


@notifications.route('/notifications/sms/firetext', methods=['POST'])
def process_firetext_response():
    if 'status' not in request.form:
        current_app.logger.info(
            "Firetext callback failed: status missing"
        )
        return jsonify(result="error", message="Firetext callback failed: status missing"), 400

    if len(request.form.get('reference', '')) <= 0:
        current_app.logger.info(
            "Firetext callback with no reference"
        )
        return jsonify(result="error", message="Firetext callback failed: reference missing"), 400

    reference = request.form['reference']
    status = request.form['status']

    if reference == 'send-sms-code':
        return jsonify(result="success", message="Firetext callback succeeded: send-sms-code"), 200

    try:
        uuid.UUID(reference, version=4)
    except ValueError:
        current_app.logger.info(
            "Firetext callback with invalid reference {}".format(reference)
        )
        return jsonify(
            result="error", message="Firetext callback with invalid reference {}".format(reference)
        ), 400

    notification_status = firetext_response_status.get(status, None)
    if not notification_status:
        current_app.logger.info(
            "Firetext callback failed: status {} not found.".format(status)
        )
        return jsonify(result="error", message="Firetext callback failed: status {} not found.".format(status)), 400

    if notifications_dao.update_notification_status_by_id(reference, notification_status['notify_status']) == 0:
        current_app.logger.info(
            "Firetext callback failed: notification {} not found. Status {}".format(reference, status)
        )
        return jsonify(
            result="error",
            message="Firetext callback failed: notification {} not found. Status {}".format(
                reference,
                notification_status['firetext_message']
            )
        ), 404

    if not notification_status['success']:
        current_app.logger.info(
            "Firetext delivery failed: notification {} has error found. Status {}".format(
                reference,
                firetext_response_status[status]['firetext_message']
            )
        )
    return jsonify(
        result="success", message="Firetext callback succeeded. reference {} updated".format(reference)
    ), 200


@notifications.route('/notifications/<string:notification_id>', methods=['GET'])
def get_notifications(notification_id):
    try:
        notification = notifications_dao.get_notification(api_user['client'], notification_id)
        return jsonify({'notification': notification_status_schema.dump(notification).data}), 200
    except NoResultFound:
        return jsonify(result="error", message="not found"), 404


@notifications.route('/notifications', methods=['GET'])
def get_all_notifications():
    page = get_page_from_request()

    if not page:
        return jsonify(result="error", message="Invalid page"), 400

    all_notifications = notifications_dao.get_notifications_for_service(api_user['client'], page)

    return jsonify(
        notifications=notification_status_schema.dump(all_notifications.items, many=True).data,
        links=pagination_links(
            all_notifications,
            '.get_all_notifications',
            request.args
        )
    ), 200


@notifications.route('/service/<service_id>/notifications', methods=['GET'])
@require_admin()
def get_all_notifications_for_service(service_id):
    page = get_page_from_request()

    if not page:
        return jsonify(result="error", message="Invalid page"), 400

    all_notifications = notifications_dao.get_notifications_for_service(service_id, page)

    return jsonify(
        notifications=notification_status_schema.dump(all_notifications.items, many=True).data,
        links=pagination_links(
            all_notifications,
            '.get_all_notifications_for_service',
            request.args
        )
    ), 200


@notifications.route('/service/<service_id>/job/<job_id>/notifications', methods=['GET'])
@require_admin()
def get_all_notifications_for_service_job(service_id, job_id):
    page = get_page_from_request()

    if not page:
        return jsonify(result="error", message="Invalid page"), 400

    all_notifications = notifications_dao.get_notifications_for_job(service_id, job_id, page)

    return jsonify(
        notifications=notification_status_schema.dump(all_notifications.items, many=True).data,
        links=pagination_links(
            all_notifications,
            '.get_all_notifications_for_service_job',
            request.args
        )
    ), 200


def get_page_from_request():
    if 'page' in request.args:
        try:
            return int(request.args['page'])

        except ValueError:
            return None
    else:
        return 1


def pagination_links(pagination, endpoint, args):
    links = dict()
    if pagination.has_prev:
        links['prev'] = url_for(endpoint, **dict(list(args.items()) + [('page', pagination.prev_num)]))
    if pagination.has_next:
        links['next'] = url_for(endpoint, **dict(list(args.items()) + [('page', pagination.next_num)]))
        links['last'] = url_for(endpoint, **dict(list(args.items()) + [('page', pagination.pages)]))
    return links


@notifications.route('/notifications/<string:notification_type>', methods=['POST'])
def send_notification(notification_type):
    if notification_type not in ['sms', 'email']:
        assert False

    service_id = api_user['client']
    service = services_dao.dao_fetch_service_by_id(api_user['client'])

    service_stats = notifications_dao.dao_get_notification_statistics_for_service_and_day(
        service_id,
        datetime.utcnow().strftime(DATE_FORMAT)
    )

    if service_stats:
        total_sms_count = service_stats.sms_requested
        total_email_count = service_stats.emails_requested

        if total_email_count + total_sms_count >= service.limit:
            return jsonify(result="error", message='Exceeded send limits ({}) for today'.format(service.limit)), 429

    notification, errors = (
        sms_template_notification_schema if notification_type == 'sms' else email_notification_schema
    ).load(request.get_json())

    if errors:
        return jsonify(result="error", message=errors), 400

    template = templates_dao.dao_get_template_by_id_and_service_id(
        template_id=notification['template'],
        service_id=service_id
    )
    if not template:
        return jsonify(
            result="error",
            message={
                'template': ['Template {} not found for service {}'.format(notification['template'], service_id)]
            }
        ), 404

    template_object = Template(template.__dict__, notification.get('personalisation', {}))
    if template_object.missing_data:
        return jsonify(
            result="error",
            message={
                'template': ['Missing personalisation: {}'.format(
                    ", ".join(template_object.missing_data)
                )]
            }
        ), 400
    if template_object.additional_data:
        return jsonify(
            result="error",
            message={
                'template': ['Personalisation not needed for template: {}'.format(
                    ", ".join(template_object.additional_data)
                )]
            }
        ), 400

    notification_id = create_uuid()

    if notification_type == 'sms':
        if service.restricted and notification['to'] not in [user.mobile_number for user in service.users]:
            return jsonify(
                result="error", message={'to': ['Invalid phone number for restricted service']}), 400
        send_sms.apply_async((
            service_id,
            notification_id,
            encryption.encrypt(notification),
            datetime.utcnow().strftime(DATETIME_FORMAT)
        ), queue='sms')
    else:
        if service.restricted and notification['to'] not in [user.email_address for user in service.users]:
            return jsonify(
                result="error", message={'to': ['Email address not permitted for restricted service']}), 400
        send_email.apply_async((
            service_id,
            notification_id,
            template.subject,
            "{}@{}".format(service.email_from, current_app.config['NOTIFY_EMAIL_DOMAIN']),
            encryption.encrypt(notification),
            datetime.utcnow().strftime(DATETIME_FORMAT)
        ), queue='email')
    return jsonify({'notification_id': notification_id}), 201
