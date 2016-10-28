from flask import request, jsonify
from app import api_user
from app.dao import services_dao, templates_dao
from app.models import SMS_TYPE
from app.notifications.process_notifications import (create_content_for_notification,
                                                     persist_notification,
                                                     send_notification_to_queue)
from app.notifications.validators import (check_service_message_limit,
                                          check_template_is_for_notification_type,
                                          check_template_is_active,
                                          service_can_send_to_recipient,
                                          check_sms_content_char_count)
from app.schema_validation import validate
from app.v2.notifications import notification_blueprint
from app.v2.notifications.notification_schemas import (post_sms_request,
                                                       create_post_sms_response_from_notification)


@notification_blueprint.route('/sms', methods=['POST'])
def post_sms_notification():
    form = validate(request.get_json(), post_sms_request)
    service = services_dao.dao_fetch_service_by_id(api_user.service_id)

    check_service_message_limit(api_user.key_type, service)
    service_can_send_to_recipient(form['phone_number'], api_user.key_type, service)

    template, content = __validate_template(form, service)

    notification = persist_notification(template_id=template.id,
                                        template_version=template.version,
                                        recipient=form['phone_number'],
                                        service_id=service.id,
                                        personalisation=form.get('personalisation', None),
                                        notification_type=SMS_TYPE,
                                        api_key_id=api_user.id,
                                        key_type=api_user.key_type)
    send_notification_to_queue(notification, service.research_mode)
    resp = create_post_sms_response_from_notification(notification, content)
    return jsonify(resp), 201


@notification_blueprint.route('/email', methods=['POST'])
def post_email_notification():
    # validate post form against post_email_request schema
    # validate service
    # validate template
    # persist notification
    # send notification to queue
    # create content
    # return post_email_response schema
    pass


def __validate_template(form, service):
    template = templates_dao.dao_get_template_by_id_and_service_id(template_id=form['template_id'],
                                                                   service_id=service.id)
    check_template_is_for_notification_type(SMS_TYPE, template.template_type)
    check_template_is_active(template)
    template_with_content = create_content_for_notification(template, form.get('personalisation', {}))
    check_sms_content_char_count(template_with_content.replaced_content_count)
    return template, template_with_content.replaced_content_count
