import functools

from flask import request, jsonify, current_app, abort

from app import api_user, authenticated_service
from app.config import QueueNames
from app.models import (
    SMS_TYPE,
    EMAIL_TYPE,
    LETTER_TYPE,
    PRIORITY,
    KEY_TYPE_TEST,
    KEY_TYPE_TEAM,
    NOTIFICATION_CREATED,
    NOTIFICATION_SENDING
)
from app.celery.tasks import update_letter_notifications_to_sent_to_dvla
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
    simulated_recipient,
    persist_scheduled_notification)
from app.notifications.process_letter_notifications import (
    create_letter_notification
)
from app.notifications.validators import (
    validate_and_format_recipient,
    check_rate_limiting,
    check_service_can_schedule_notification,
    check_service_has_permission,
    validate_template,
    check_service_email_reply_to_id
)
from app.schema_validation import validate
from app.v2.errors import BadRequestError
from app.v2.notifications import v2_notification_blueprint
from app.v2.notifications.notification_schemas import (
    post_sms_request,
    post_email_request,
    post_letter_request
)
from app.v2.notifications.create_response import (
    create_post_sms_response_from_notification,
    create_post_email_response_from_notification,
    create_post_letter_response_from_notification
)


@v2_notification_blueprint.route('/<notification_type>', methods=['POST'])
def post_notification(notification_type):
    if notification_type == EMAIL_TYPE:
        form = validate(request.get_json(), post_email_request)
    elif notification_type == SMS_TYPE:
        form = validate(request.get_json(), post_sms_request)
    elif notification_type == LETTER_TYPE:
        form = validate(request.get_json(), post_letter_request)
    else:
        abort(404)

    check_service_has_permission(notification_type, authenticated_service.permissions)

    scheduled_for = form.get("scheduled_for", None)
    service_email_reply_to_id = form.get("email_reply_to_id", None)

    check_service_can_schedule_notification(authenticated_service.permissions, scheduled_for)

    check_rate_limiting(authenticated_service, api_user)

    check_service_email_reply_to_id(str(authenticated_service.id), service_email_reply_to_id)

    template, template_with_content = validate_template(
        form['template_id'],
        form.get('personalisation', {}),
        authenticated_service,
        notification_type,
    )

    if notification_type == LETTER_TYPE:
        notification = process_letter_notification(
            letter_data=form,
            api_key=api_user,
            template=template,
        )
    else:
        notification = process_sms_or_email_notification(
            form=form,
            notification_type=notification_type,
            api_key=api_user,
            template=template,
            service=authenticated_service
        )

    if notification_type == SMS_TYPE:
        create_resp_partial = functools.partial(
            create_post_sms_response_from_notification,
            from_number=authenticated_service.get_inbound_number()
        )
    elif notification_type == EMAIL_TYPE:
        create_resp_partial = functools.partial(
            create_post_email_response_from_notification,
            subject=template_with_content.subject,
            email_from='{}@{}'.format(authenticated_service.email_from, current_app.config['NOTIFY_EMAIL_DOMAIN'])
        )
    elif notification_type == LETTER_TYPE:
        create_resp_partial = functools.partial(
            create_post_letter_response_from_notification,
            subject=template_with_content.subject,
        )

    resp = create_resp_partial(
        notification=notification,
        content=str(template_with_content),
        url_root=request.url_root,
        scheduled_for=scheduled_for
    )
    return jsonify(resp), 201


def process_sms_or_email_notification(*, form, notification_type, api_key, template, service):
    form_send_to = form['email_address'] if notification_type == EMAIL_TYPE else form['phone_number']

    send_to = validate_and_format_recipient(send_to=form_send_to,
                                            key_type=api_key.key_type,
                                            service=service,
                                            notification_type=notification_type)

    # Do not persist or send notification to the queue if it is a simulated recipient
    simulated = simulated_recipient(send_to, notification_type)

    notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=form_send_to,
        service=service,
        personalisation=form.get('personalisation', None),
        notification_type=notification_type,
        api_key_id=api_key.id,
        key_type=api_key.key_type,
        client_reference=form.get('reference', None),
        simulated=simulated
    )

    scheduled_for = form.get("scheduled_for", None)
    if scheduled_for:
        persist_scheduled_notification(notification.id, form["scheduled_for"])
    else:
        if not simulated:
            queue_name = QueueNames.PRIORITY if template.process_type == PRIORITY else None
            send_notification_to_queue(
                notification=notification,
                research_mode=service.research_mode,
                queue=queue_name
            )
        else:
            current_app.logger.info("POST simulated notification for id: {}".format(notification.id))

    return notification


def process_letter_notification(*, letter_data, api_key, template):
    if api_key.key_type == KEY_TYPE_TEAM:
        raise BadRequestError(message='Cannot send letters with a team api key', status_code=403)

    if api_key.service.restricted and api_key.key_type != KEY_TYPE_TEST:
        raise BadRequestError(message='Cannot send letters when service is in trial mode', status_code=403)

    should_send = not (api_key.service.research_mode or api_key.key_type == KEY_TYPE_TEST)

    # if we don't want to actually send the letter, then start it off in SENDING so we don't pick it up
    status = NOTIFICATION_CREATED if should_send else NOTIFICATION_SENDING

    notification = create_letter_notification(letter_data, template, api_key, status=status)

    if not should_send:
        update_letter_notifications_to_sent_to_dvla.apply_async(
            kwargs={'notification_references': [notification.reference]},
            queue=QueueNames.RESEARCH_MODE
        )

    return notification
