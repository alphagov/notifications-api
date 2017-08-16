import functools

from flask import request, jsonify, current_app, abort

from app import api_user, authenticated_service
from app.config import QueueNames
from app.dao.jobs_dao import dao_update_job
from app.models import SMS_TYPE, EMAIL_TYPE, LETTER_TYPE, PRIORITY, KEY_TYPE_TEST, KEY_TYPE_TEAM
from app.celery.tasks import build_dvla_file, update_job_to_sent_to_dvla
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
    simulated_recipient,
    persist_scheduled_notification)
from app.notifications.process_letter_notifications import (
    create_letter_api_job,
    create_letter_notification
)
from app.notifications.validators import (
    validate_and_format_recipient,
    check_rate_limiting,
    check_service_can_schedule_notification,
    check_service_has_permission,
    validate_template
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
from app.variables import LETTER_TEST_API_FILENAME


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
    check_service_can_schedule_notification(authenticated_service.permissions, scheduled_for)

    check_rate_limiting(authenticated_service, api_user)

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
        sms_sender = authenticated_service.sms_sender or current_app.config.get('FROM_NUMBER')
        create_resp_partial = functools.partial(
            create_post_sms_response_from_notification,
            from_number=sms_sender
        )
    elif notification_type == EMAIL_TYPE:
        create_resp_partial = functools.partial(
            create_post_email_response_from_notification,
            subject=template_with_content.subject,
            email_from=authenticated_service.email_from
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

    job = create_letter_api_job(template)
    notification = create_letter_notification(letter_data, job, api_key)

    if api_key.service.research_mode or api_key.key_type == KEY_TYPE_TEST:

        # distinguish real API jobs from test jobs by giving the test jobs a different filename
        job.original_file_name = LETTER_TEST_API_FILENAME
        dao_update_job(job)

        update_job_to_sent_to_dvla.apply_async([str(job.id)], queue=QueueNames.RESEARCH_MODE)
    else:
        build_dvla_file.apply_async([str(job.id)], queue=QueueNames.JOBS)

    current_app.logger.info("send job {} for api notification {} to build-dvla-file in the process-job queue".format(
        job.id,
        notification.id
    ))
    return notification
