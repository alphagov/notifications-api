from flask import request, jsonify, current_app
from sqlalchemy.orm.exc import NoResultFound

from app import api_user
from app.dao import services_dao, templates_dao
from app.models import SMS_TYPE, EMAIL_TYPE, PRIORITY
from app.notifications.process_notifications import (create_content_for_notification,
                                                     persist_notification,
                                                     send_notification_to_queue,
                                                     simulated_recipient)
from app.notifications.validators import (check_service_message_limit,
                                          check_template_is_for_notification_type,
                                          check_template_is_active,
                                          check_sms_content_char_count,
                                          validate_and_format_recipient)
from app.schema_validation import validate
from app.v2.errors import BadRequestError
from app.v2.notifications import v2_notification_blueprint
from app.v2.notifications.notification_schemas import (post_sms_request,
                                                       create_post_sms_response_from_notification, post_email_request,
                                                       create_post_email_response_from_notification)


@v2_notification_blueprint.route('/<notification_type>', methods=['POST'])
def post_notification(notification_type):
    if notification_type == EMAIL_TYPE:
        form = validate(request.get_json(), post_email_request)
    else:
        form = validate(request.get_json(), post_sms_request)

    service = services_dao.dao_fetch_service_by_id(api_user.service_id)
    check_service_message_limit(api_user.key_type, service)
    form_send_to = form['phone_number'] if notification_type == SMS_TYPE else form['email_address']
    send_to = validate_and_format_recipient(send_to=form_send_to,
                                            key_type=api_user.key_type,
                                            service=service,
                                            notification_type=notification_type)

    template, template_with_content = __validate_template(form, service, notification_type)

    # Do not persist or send notification to the queue if it is a simulated recipient
    simulated = simulated_recipient(send_to, notification_type)
    notification = persist_notification(template_id=template.id,
                                        template_version=template.version,
                                        recipient=form_send_to,
                                        service=service,
                                        personalisation=form.get('personalisation', None),
                                        notification_type=notification_type,
                                        api_key_id=api_user.id,
                                        key_type=api_user.key_type,
                                        client_reference=form.get('reference', None),
                                        simulated=simulated)
    if not simulated:
        queue_name = 'priority' if template.process_type == PRIORITY else None
        send_notification_to_queue(notification=notification, research_mode=service.research_mode, queue=queue_name)
    else:
        current_app.logger.info("POST simulated notification for id: {}".format(notification.id))
    if notification_type == SMS_TYPE:
        sms_sender = service.sms_sender if service.sms_sender else current_app.config.get('FROM_NUMBER')
        resp = create_post_sms_response_from_notification(notification=notification,
                                                          body=str(template_with_content),
                                                          from_number=sms_sender,
                                                          url_root=request.url_root,
                                                          service_id=service.id)
    else:
        resp = create_post_email_response_from_notification(notification=notification,
                                                            content=str(template_with_content),
                                                            subject=template_with_content.subject,
                                                            email_from=service.email_from,
                                                            url_root=request.url_root,
                                                            service_id=service.id)
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
    if template.template_type == SMS_TYPE:
        check_sms_content_char_count(template_with_content.content_count)
    return template, template_with_content
