from flask import request, jsonify
from sqlalchemy.orm.exc import NoResultFound

from app import api_user
from app.dao import services_dao, templates_dao
from app.models import SMS_TYPE, EMAIL_TYPE
from app.notifications.process_notifications import (create_content_for_notification,
                                                     persist_notification,
                                                     send_notification_to_queue)
from app.notifications.validators import (check_service_message_limit,
                                          check_template_is_for_notification_type,
                                          check_template_is_active,
                                          service_can_send_to_recipient,
                                          check_sms_content_char_count)
from app.schema_validation import validate
from app.v2.errors import BadRequestError
from app.v2.notifications import notification_blueprint
from app.v2.notifications.notification_schemas import (post_sms_request,
                                                       create_post_sms_response_from_notification, post_email_request,
                                                       create_post_email_response_from_notification)


@notification_blueprint.route('/sms', methods=['POST'])
def post_sms_notification():
    form = validate(request.get_json(), post_sms_request)
    service = services_dao.dao_fetch_service_by_id(api_user.service_id)

    check_service_message_limit(api_user.key_type, service)
    service_can_send_to_recipient(form['phone_number'], api_user.key_type, service)

    template, template_with_content = __validate_template(form, service, SMS_TYPE)

    notification = persist_notification(template_id=template.id,
                                        template_version=template.version,
                                        recipient=form['phone_number'],
                                        service_id=service.id,
                                        personalisation=form.get('personalisation', None),
                                        notification_type=SMS_TYPE,
                                        api_key_id=api_user.id,
                                        key_type=api_user.key_type,
                                        reference=form.get('reference'))
    send_notification_to_queue(notification, service.research_mode)

    resp = create_post_sms_response_from_notification(notification,
                                                      template_with_content.rendered,
                                                      service.sms_sender,
                                                      request.url_root)
    return jsonify(resp), 201


@notification_blueprint.route('/email', methods=['POST'])
def post_email_notification():
    form = validate(request.get_json(), post_email_request)
    service = services_dao.dao_fetch_service_by_id(api_user.service_id)

    check_service_message_limit(api_user.key_type, service)
    service_can_send_to_recipient(form['email_address'], api_user.key_type, service)

    template, template_with_content = __validate_template(form, service, EMAIL_TYPE)
    notification = persist_notification(template_id=template.id,
                                        template_version=template.version,
                                        recipient=form['email_address'],
                                        service_id=service.id,
                                        personalisation=form.get('personalisation', None),
                                        notification_type=EMAIL_TYPE,
                                        api_key_id=api_user.id,
                                        key_type=api_user.key_type,
                                        reference=form.get('reference'))

    send_notification_to_queue(notification, service.research_mode)

    resp = create_post_email_response_from_notification(notification=notification,
                                                        content=template_with_content.rendered,
                                                        subject=template_with_content.subject,
                                                        email_from=service.email_from,
                                                        url_root=request.url_root)
    return jsonify(resp), 201


def __validate_template(form, service, notification_type):
    try:
        template = templates_dao.dao_get_template_by_id_and_service_id(template_id=form['template_id'],
                                                                       service_id=service.id)
    except NoResultFound:
        message = 'Template not found'
        raise BadRequestError(message=message,
                              fields=[{'template': message}])

    check_template_is_for_notification_type(notification_type, template.template_type)
    check_template_is_active(template)
    template_with_content = create_content_for_notification(template, form.get('personalisation', {}))
    check_sms_content_char_count(template_with_content.content_count)
    return template, template_with_content
