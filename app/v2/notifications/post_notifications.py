from flask import request, jsonify, current_app

from app import api_user, authenticated_service
from app.models import SMS_TYPE, EMAIL_TYPE, PRIORITY
from app.celery import QueueNames
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
    simulated_recipient,
    persist_scheduled_notification)
from app.notifications.validators import (
    validate_and_format_recipient,
    check_rate_limiting,
    check_service_can_schedule_notification,
    check_service_has_permission,
    validate_template
)
from app.schema_validation import validate
from app.v2.notifications import v2_notification_blueprint
from app.v2.notifications.notification_schemas import (
    post_sms_request,
    create_post_sms_response_from_notification,
    post_email_request,
    create_post_email_response_from_notification)


@v2_notification_blueprint.route('/<notification_type>', methods=['POST'])
def post_notification(notification_type):
    if notification_type == EMAIL_TYPE:
        form = validate(request.get_json(), post_email_request)
    else:
        form = validate(request.get_json(), post_sms_request)

    check_service_has_permission(notification_type, authenticated_service.permissions)

    scheduled_for = form.get("scheduled_for", None)
    check_service_can_schedule_notification(authenticated_service.permissions, scheduled_for)

    check_rate_limiting(authenticated_service, api_user)

    form_send_to = form['phone_number'] if notification_type == SMS_TYPE else form['email_address']
    send_to = validate_and_format_recipient(send_to=form_send_to,
                                            key_type=api_user.key_type,
                                            service=authenticated_service,
                                            notification_type=notification_type)

    template, template_with_content = validate_template(
        form['template_id'],
        form.get('personalisation', {}),
        authenticated_service,
        notification_type,
    )

    # Do not persist or send notification to the queue if it is a simulated recipient
    simulated = simulated_recipient(send_to, notification_type)

    notification = persist_notification(template_id=template.id,
                                        template_version=template.version,
                                        recipient=form_send_to,
                                        service=authenticated_service,
                                        personalisation=form.get('personalisation', None),
                                        notification_type=notification_type,
                                        api_key_id=api_user.id,
                                        key_type=api_user.key_type,
                                        client_reference=form.get('reference', None),
                                        simulated=simulated)

    if scheduled_for:
        persist_scheduled_notification(notification.id, form["scheduled_for"])
    else:
        if not simulated:
            queue_name = QueueNames.PRIORITY if template.process_type == PRIORITY else None
            send_notification_to_queue(
                notification=notification,
                research_mode=authenticated_service.research_mode,
                queue=queue_name
            )
        else:
            current_app.logger.info("POST simulated notification for id: {}".format(notification.id))

    if notification_type == SMS_TYPE:
        sms_sender = authenticated_service.sms_sender or current_app.config.get('FROM_NUMBER')
        resp = create_post_sms_response_from_notification(notification=notification,
                                                          body=str(template_with_content),
                                                          from_number=sms_sender,
                                                          url_root=request.url_root,
                                                          service_id=authenticated_service.id,
                                                          scheduled_for=scheduled_for)
    else:
        resp = create_post_email_response_from_notification(notification=notification,
                                                            content=str(template_with_content),
                                                            subject=template_with_content.subject,
                                                            email_from=authenticated_service.email_from,
                                                            url_root=request.url_root,
                                                            service_id=authenticated_service.id,
                                                            scheduled_for=scheduled_for)
    return jsonify(resp), 201
