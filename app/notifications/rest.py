from datetime import datetime
import itertools

from flask import (
    Blueprint,
    jsonify,
    request,
    current_app,
    json
)

from notifications_utils.recipients import allowed_to_send_to, first_column_heading
from notifications_utils.template import Template
from notifications_utils.renderers import PassThrough
from app.clients.email.aws_ses import get_aws_responses
from app import api_user, encryption, create_uuid, DATETIME_FORMAT, DATE_FORMAT, statsd_client
from app.dao.notifications_dao import dao_create_notification
from app.dao.services_dao import dao_fetch_todays_stats_for_service
from app.models import KEY_TYPE_TEAM, KEY_TYPE_TEST, Notification, KEY_TYPE_NORMAL, EMAIL_TYPE
from app.dao import (
    templates_dao,
    services_dao,
    notifications_dao
)
from app.models import SMS_TYPE
from app.notifications.process_client_response import (
    validate_callback_data,
    process_sms_client_response
)
from app.schemas import (
    email_notification_schema,
    sms_template_notification_schema,
    notification_with_personalisation_schema,
    notifications_filter_schema,
    notifications_statistics_schema,
    day_schema,
    unarchived_template_schema
)
from app.celery.tasks import send_sms, send_email
from app.utils import pagination_links

notifications = Blueprint('notifications', __name__)

from app.errors import (
    register_errors,
    InvalidRequest
)

register_errors(notifications)
from app.celery.provider_tasks import send_sms_to_provider, send_email_to_provider


@notifications.route('/notifications/email/ses', methods=['POST'])
def process_ses_response():
    client_name = 'SES'
    try:
        ses_request = json.loads(request.data)
        errors = validate_callback_data(data=ses_request, fields=['Message'], client_name=client_name)
        if errors:
            raise InvalidRequest(errors, status_code=400)

        ses_message = json.loads(ses_request['Message'])
        errors = validate_callback_data(data=ses_message, fields=['notificationType'], client_name=client_name)
        if errors:
            raise InvalidRequest(errors, status_code=400)

        notification_type = ses_message['notificationType']
        if notification_type == 'Bounce':
            if ses_message['bounce']['bounceType'] == 'Permanent':
                notification_type = ses_message['bounce']['bounceType']  # permanent or not
            else:
                notification_type = 'Temporary'
        try:
            aws_response_dict = get_aws_responses(notification_type)
        except KeyError:
            error = "{} callback failed: status {} not found".format(client_name, notification_type)
            raise InvalidRequest(error, status_code=400)

        notification_status = aws_response_dict['notification_status']

        try:
            reference = ses_message['mail']['messageId']
            if not notifications_dao.update_notification_status_by_reference(
                    reference,
                    notification_status
            ):
                error = "SES callback failed: notification either not found or already updated " \
                        "from sending. Status {}".format(notification_status)
                raise InvalidRequest(error, status_code=404)

            if not aws_response_dict['success']:
                current_app.logger.info(
                    "SES delivery failed: notification {} has error found. Status {}".format(
                        reference,
                        aws_response_dict['message']
                    )
                )

            statsd_client.incr('callback.ses.{}'.format(notification_status))
            return jsonify(
                result="success", message="SES callback succeeded"
            ), 200

        except KeyError:
            message = "SES callback failed: messageId missing"
            raise InvalidRequest(message, status_code=400)

    except ValueError as ex:
        error = "{} callback failed: invalid json".format(client_name)
        raise InvalidRequest(error, status_code=400)


@notifications.route('/notifications/sms/mmg', methods=['POST'])
def process_mmg_response():
    client_name = 'MMG'
    data = json.loads(request.data)
    errors = validate_callback_data(data=data,
                                    fields=['status', 'CID'],
                                    client_name=client_name)
    if errors:
        raise InvalidRequest(errors, status_code=400)

    success, errors = process_sms_client_response(status=str(data.get('status')),
                                                  reference=data.get('CID'),
                                                  client_name=client_name)
    if errors:
        raise InvalidRequest(errors, status_code=400)
    else:
        return jsonify(result='success', message=success), 200


@notifications.route('/notifications/sms/firetext', methods=['POST'])
def process_firetext_response():
    client_name = 'Firetext'
    errors = validate_callback_data(data=request.form,
                                    fields=['status', 'reference'],
                                    client_name=client_name)
    if errors:
        raise InvalidRequest(errors, status_code=400)

    response_code = request.form.get('code')
    status = request.form.get('status')
    current_app.logger.info('Firetext status: {}, extended error code: {}'.format(status, response_code))

    success, errors = process_sms_client_response(status=status,
                                                  reference=request.form.get('reference'),
                                                  client_name=client_name)
    if errors:
        raise InvalidRequest(errors, status_code=400)
    else:
        return jsonify(result='success', message=success), 200


@notifications.route('/notifications/<uuid:notification_id>', methods=['GET'])
def get_notification_by_id(notification_id):
    notification = notifications_dao.get_notification_with_personalisation(str(api_user.service_id),
                                                                           notification_id,
                                                                           key_type=api_user.key_type)
    return jsonify(data={"notification": notification_with_personalisation_schema.dump(notification).data}), 200


@notifications.route('/notifications', methods=['GET'])
def get_all_notifications():
    data = notifications_filter_schema.load(request.args).data
    page = data['page'] if 'page' in data else 1
    page_size = data['page_size'] if 'page_size' in data else current_app.config.get('PAGE_SIZE')
    limit_days = data.get('limit_days')

    pagination = notifications_dao.get_notifications_for_service(
        str(api_user.service_id),
        personalisation=True,
        filter_dict=data,
        page=page,
        page_size=page_size,
        limit_days=limit_days,
        key_type=api_user.key_type)
    return jsonify(
        notifications=notification_with_personalisation_schema.dump(pagination.items, many=True).data,
        page_size=page_size,
        total=pagination.total,
        links=pagination_links(
            pagination,
            '.get_all_notifications',
            **request.args.to_dict()
        )
    ), 200


@notifications.route('/notifications/<string:notification_type>', methods=['POST'])
def send_notification(notification_type):
    if notification_type not in ['sms', 'email']:
        assert False

    service_id = str(api_user.service_id)
    service = services_dao.dao_fetch_service_by_id(service_id)

    notification, errors = (
        sms_template_notification_schema if notification_type == SMS_TYPE else email_notification_schema
    ).load(request.get_json())

    if all((api_user.key_type != KEY_TYPE_TEST, service.restricted)):
        service_stats = sum(row.count for row in dao_fetch_todays_stats_for_service(service.id))
        if service_stats >= service.message_limit:
            error = 'Exceeded send limits ({}) for today'.format(service.message_limit)
            raise InvalidRequest(error, status_code=429)

    if errors:
        raise InvalidRequest(errors, status_code=400)

    template = templates_dao.dao_get_template_by_id_and_service_id(
        template_id=notification['template'],
        service_id=service_id
    )

    errors = unarchived_template_schema.validate({'archived': template.archived})
    if errors:
        raise InvalidRequest(errors, status_code=400)

    template_object = Template(
        template.__dict__,
        notification.get('personalisation', {}),
        renderer=PassThrough()
    )
    if template_object.missing_data:
        message = 'Missing personalisation: {}'.format(", ".join(template_object.missing_data))
        errors = {'template': [message]}
        raise InvalidRequest(errors, status_code=400)

    if template_object.additional_data:
        message = 'Personalisation not needed for template: {}'.format(", ".join(template_object.additional_data))
        errors = {'template': [message]}
        raise InvalidRequest(errors, status_code=400)

    if (
            template_object.template_type == SMS_TYPE and
            template_object.replaced_content_count > current_app.config.get('SMS_CHAR_COUNT_LIMIT')
    ):
        char_count = current_app.config.get('SMS_CHAR_COUNT_LIMIT')
        message = 'Content has a character count greater than the limit of {}'.format(char_count)
        errors = {'content': [message]}
        raise InvalidRequest(errors, status_code=400)

    if all((
            api_user.key_type != KEY_TYPE_TEST,
            service.restricted or api_user.key_type == KEY_TYPE_TEAM,
            not allowed_to_send_to(
                notification['to'],
                itertools.chain.from_iterable(
                    [user.mobile_number, user.email_address] for user in service.users
                )
            )
    )):
        if (api_user.key_type == KEY_TYPE_TEAM):
            message = 'Can’t send to this recipient using a team-only API key'
        else:
            message = (
                'Can’t send to this recipient when service is in trial mode '
                '– see https://www.notifications.service.gov.uk/trial-mode'
            )
        raise InvalidRequest(
            {'to': [message]},
            status_code=400
        )

    notification_id = create_uuid()
    notification.update({"template_version": template.version})
    persist_notification(
        service,
        notification_id,
        notification,
        datetime.utcnow().strftime(DATETIME_FORMAT),
        notification_type,
        str(api_user.id),
        api_user.key_type
    )

    return jsonify(
        data=get_notification_return_data(
            notification_id,
            notification,
            template_object)
    ), 201


def get_notification_return_data(notification_id, notification, template):
    output = {
        'body': template.replaced,
        'template_version': notification['template_version'],
        'notification': {'id': notification_id}
    }

    if template.template_type == 'email':
        output.update({'subject': template.replaced_subject})

    return output


@notifications.route('/notifications/statistics')
def get_notification_statistics_for_day():
    data = day_schema.load(request.args).data
    statistics = notifications_dao.dao_get_potential_notification_statistics_for_day(
        day=data['day']
    )
    data, errors = notifications_statistics_schema.dump(statistics, many=True)
    return jsonify(data=data), 200


def persist_notification(
        service,
        notification_id,
        notification,
        created_at,
        notification_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
):
    dao_create_notification(
        Notification.from_api_request(
            created_at, notification, notification_id, service.id, notification_type, api_key_id, key_type
        )
    )

    if notification_type == SMS_TYPE:
        send_sms_to_provider.apply_async((str(service.id), str(notification_id)), queue='send-sms')
    if notification_type == EMAIL_TYPE:
        send_email_to_provider.apply_async((str(service.id), str(notification_id)), queue='send-email')

    current_app.logger.info(
        "{} {} created at {}".format(notification_type, notification_id, created_at)
    )
