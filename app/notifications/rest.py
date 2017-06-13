from flask import (
    Blueprint,
    jsonify,
    request,
    current_app
)

from app import api_user, authenticated_service
from app.config import QueueNames
from app.dao import (
    templates_dao,
    notifications_dao
)
from app.errors import (
    register_errors,
    InvalidRequest
)
from app.models import KEY_TYPE_TEAM, PRIORITY
from app.models import SMS_TYPE
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
    simulated_recipient
)
from app.notifications.validators import (
    check_template_is_for_notification_type,
    check_template_is_active,
    check_rate_limiting
)
from app.schemas import (
    email_notification_schema,
    sms_template_notification_schema,
    notification_with_personalisation_schema,
    notifications_filter_schema,
    notifications_statistics_schema,
    day_schema
)
from app.service.utils import service_allowed_to_send_to
from app.utils import pagination_links, get_template_instance

from notifications_utils.recipients import get_international_phone_info

notifications = Blueprint('notifications', __name__)

register_errors(notifications)


@notifications.route('/notifications/<uuid:notification_id>', methods=['GET'])
def get_notification_by_id(notification_id):
    notification = notifications_dao.get_notification_with_personalisation(
        str(authenticated_service.id),
        notification_id,
        key_type=None)
    return jsonify(data={"notification": notification_with_personalisation_schema.dump(notification).data}), 200


@notifications.route('/notifications', methods=['GET'])
def get_all_notifications():
    data = notifications_filter_schema.load(request.args).data
    include_jobs = data.get('include_jobs', False)
    page = data.get('page', 1)
    page_size = data.get('page_size', current_app.config.get('API_PAGE_SIZE'))
    limit_days = data.get('limit_days')

    pagination = notifications_dao.get_notifications_for_service(
        str(authenticated_service.id),
        personalisation=True,
        filter_dict=data,
        page=page,
        page_size=page_size,
        limit_days=limit_days,
        key_type=api_user.key_type,
        include_jobs=include_jobs)
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


@notifications.route('/notifications/statistics')
def get_notification_statistics_for_day():
    data = day_schema.load(request.args).data
    statistics = notifications_dao.dao_get_potential_notification_statistics_for_day(
        day=data['day']
    )
    data, errors = notifications_statistics_schema.dump(statistics, many=True)
    return jsonify(data=data), 200


@notifications.route('/notifications/<string:notification_type>', methods=['POST'])
def send_notification(notification_type):

    if notification_type not in ['sms', 'email']:
        assert False

    notification_form, errors = (
        sms_template_notification_schema if notification_type == SMS_TYPE else email_notification_schema
    ).load(request.get_json())

    if errors:
        raise InvalidRequest(errors, status_code=400)

    check_rate_limiting(authenticated_service, api_user)

    template = templates_dao.dao_get_template_by_id_and_service_id(
        template_id=notification_form['template'],
        service_id=authenticated_service.id)

    check_template_is_for_notification_type(notification_type, template.template_type)
    check_template_is_active(template)

    template_object = create_template_object_for_notification(template, notification_form.get('personalisation', {}))

    _service_allowed_to_send_to(notification_form, authenticated_service)
    if notification_type == SMS_TYPE:
        _service_can_send_internationally(authenticated_service, notification_form['to'])

    # Do not persist or send notification to the queue if it is a simulated recipient
    simulated = simulated_recipient(notification_form['to'], notification_type)
    notification_model = persist_notification(template_id=template.id,
                                              template_version=template.version,
                                              recipient=request.get_json()['to'],
                                              service=authenticated_service,
                                              personalisation=notification_form.get('personalisation', None),
                                              notification_type=notification_type,
                                              api_key_id=api_user.id,
                                              key_type=api_user.key_type,
                                              simulated=simulated)
    if not simulated:
        queue_name = QueueNames.PRIORITY if template.process_type == PRIORITY else None
        send_notification_to_queue(notification=notification_model,
                                   research_mode=authenticated_service.research_mode,
                                   queue=queue_name)
    else:
        current_app.logger.info("POST simulated notification for id: {}".format(notification_model.id))
    notification_form.update({"template_version": template.version})

    return jsonify(
        data=get_notification_return_data(
            notification_model.id,
            notification_form,
            template_object)
    ), 201


def get_notification_return_data(notification_id, notification, template):
    output = {
        'body': str(template),
        'template_version': notification['template_version'],
        'notification': {'id': notification_id}
    }

    if template.template_type == 'email':
        output.update({'subject': template.subject})

    return output


def _service_can_send_internationally(service, number):
    international_phone_info = get_international_phone_info(number)

    if international_phone_info.international and not service.can_send_international_sms:
        raise InvalidRequest(
            {'to': ["Cannot send to international mobile numbers"]},
            status_code=400
        )


def _service_allowed_to_send_to(notification, service):
    if not service_allowed_to_send_to(notification['to'], service, api_user.key_type):
        if api_user.key_type == KEY_TYPE_TEAM:
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


def create_template_object_for_notification(template, personalisation):
    template_object = get_template_instance(template.__dict__, personalisation)

    if template_object.missing_data:
        message = 'Missing personalisation: {}'.format(", ".join(template_object.missing_data))
        errors = {'template': [message]}
        raise InvalidRequest(errors, status_code=400)

    if (
        template_object.template_type == SMS_TYPE and
        template_object.content_count > current_app.config.get('SMS_CHAR_COUNT_LIMIT')
    ):
        char_count = current_app.config.get('SMS_CHAR_COUNT_LIMIT')
        message = 'Content has a character count greater than the limit of {}'.format(char_count)
        errors = {'content': [message]}
        raise InvalidRequest(errors, status_code=400)
    return template_object
