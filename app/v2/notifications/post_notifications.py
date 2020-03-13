import base64
import functools

from flask import request, jsonify, current_app, abort
from notifications_utils.recipients import (
    format_postcode_for_printing, is_a_real_uk_postcode, try_validate_and_format_phone_number
)

from app import api_user, authenticated_service, notify_celery, document_download_client
from app.celery.letters_pdf_tasks import create_letters_pdf, process_virus_scan_passed
from app.celery.research_mode_tasks import create_fake_letter_response_file
from app.clients.document_download import DocumentDownloadError
from app.config import QueueNames, TaskNames
from app.dao.notifications_dao import update_notification_status_by_reference
from app.dao.templates_dao import get_precompiled_letter_template
from app.letters.utils import upload_letter_pdf
from app.models import (
    SMS_TYPE,
    EMAIL_TYPE,
    LETTER_TYPE,
    PRIORITY,
    KEY_TYPE_TEST,
    KEY_TYPE_TEAM,
    NOTIFICATION_CREATED,
    NOTIFICATION_SENDING,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING_VIRUS_CHECK,
)
from app.notifications.process_letter_notifications import (
    create_letter_notification
)
from app.notifications.process_notifications import (
    persist_notification,
    persist_scheduled_notification,
    send_notification_to_queue,
    simulated_recipient
)
from app.notifications.validators import (
    check_if_service_can_send_files_by_email,
    check_rate_limiting,
    check_service_can_schedule_notification,
    check_service_email_reply_to_id,
    check_service_has_permission,
    check_service_sms_sender_id,
    validate_and_format_recipient,
    validate_template,
)
from app.schema_validation import validate
from app.v2.errors import BadRequestError, ValidationError
from app.v2.notifications import v2_notification_blueprint
from app.v2.notifications.create_response import (
    create_post_sms_response_from_notification,
    create_post_email_response_from_notification,
    create_post_letter_response_from_notification
)
from app.v2.notifications.notification_schemas import (
    post_sms_request,
    post_email_request,
    post_letter_request,
    post_precompiled_letter_request
)
from app.v2.utils import get_valid_json


@v2_notification_blueprint.route('/{}'.format(LETTER_TYPE), methods=['POST'])
def post_precompiled_letter_notification():
    request_json = get_valid_json()
    if 'content' not in (request_json or {}):
        return post_notification(LETTER_TYPE)

    form = validate(request_json, post_precompiled_letter_request)

    # Check permission to send letters
    check_service_has_permission(LETTER_TYPE, authenticated_service.permissions)

    check_rate_limiting(authenticated_service, api_user)

    template = get_precompiled_letter_template(authenticated_service.id)

    # For precompiled letters the to field will be set to Provided as PDF until the validation passes,
    # then the address of the letter will be set as the to field
    form['personalisation'] = {
        'address_line_1': 'Provided as PDF'
    }

    reply_to = get_reply_to_text(LETTER_TYPE, form, template)

    notification = process_letter_notification(
        letter_data=form,
        api_key=api_user,
        template=template,
        reply_to_text=reply_to,
        precompiled=True
    )

    resp = {
        'id': notification.id,
        'reference': notification.client_reference,
        'postage': notification.postage
    }

    return jsonify(resp), 201


@v2_notification_blueprint.route('/<notification_type>', methods=['POST'])
def post_notification(notification_type):
    request_json = get_valid_json()

    if notification_type == EMAIL_TYPE:
        form = validate(request_json, post_email_request)
    elif notification_type == SMS_TYPE:
        form = validate(request_json, post_sms_request)
    elif notification_type == LETTER_TYPE:
        form = validate(request_json, post_letter_request)
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

    reply_to = get_reply_to_text(notification_type, form, template)

    if notification_type == LETTER_TYPE:
        notification = process_letter_notification(
            letter_data=form,
            api_key=api_user,
            template=template,
            reply_to_text=reply_to
        )
    else:
        notification = process_sms_or_email_notification(
            form=form,
            notification_type=notification_type,
            api_key=api_user,
            template=template,
            service=authenticated_service,
            reply_to_text=reply_to
        )

        template_with_content.values = notification.personalisation

    if notification_type == SMS_TYPE:
        create_resp_partial = functools.partial(
            create_post_sms_response_from_notification,
            from_number=reply_to
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


def process_sms_or_email_notification(*, form, notification_type, api_key, template, service, reply_to_text=None):
    form_send_to = form['email_address'] if notification_type == EMAIL_TYPE else form['phone_number']

    send_to = validate_and_format_recipient(send_to=form_send_to,
                                            key_type=api_key.key_type,
                                            service=service,
                                            notification_type=notification_type)

    # Do not persist or send notification to the queue if it is a simulated recipient
    simulated = simulated_recipient(send_to, notification_type)

    personalisation, document_download_count = process_document_uploads(
        form.get('personalisation'),
        service,
        simulated=simulated
    )

    notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=form_send_to,
        service=service,
        personalisation=personalisation,
        notification_type=notification_type,
        api_key_id=api_key.id,
        key_type=api_key.key_type,
        client_reference=form.get('reference', None),
        simulated=simulated,
        reply_to_text=reply_to_text,
        document_download_count=document_download_count
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
            current_app.logger.debug("POST simulated notification for id: {}".format(notification.id))

    return notification


def process_document_uploads(personalisation_data, service, simulated=False):
    """
    Returns modified personalisation dict and a count of document uploads. If there are no document uploads, returns
    a count of `None` rather than `0`.
    """
    file_keys = [k for k, v in (personalisation_data or {}).items() if isinstance(v, dict) and 'file' in v]
    if not file_keys:
        return personalisation_data, None

    personalisation_data = personalisation_data.copy()

    check_if_service_can_send_files_by_email(
        service_contact_link=authenticated_service.contact_link,
        service_id=authenticated_service.id
    )

    for key in file_keys:
        if simulated:
            personalisation_data[key] = document_download_client.get_upload_url(service.id) + '/test-document'
        else:
            try:
                personalisation_data[key] = document_download_client.upload_document(
                    service.id, personalisation_data[key]['file']
                )
            except DocumentDownloadError as e:
                raise BadRequestError(message=e.message, status_code=e.status_code)

    return personalisation_data, len(file_keys)


def process_letter_notification(*, letter_data, api_key, template, reply_to_text, precompiled=False):
    if api_key.key_type == KEY_TYPE_TEAM:
        raise BadRequestError(message='Cannot send letters with a team api key', status_code=403)

    if not api_key.service.research_mode and api_key.service.restricted and api_key.key_type != KEY_TYPE_TEST:
        raise BadRequestError(message='Cannot send letters when service is in trial mode', status_code=403)

    if precompiled:
        return process_precompiled_letter_notifications(letter_data=letter_data,
                                                        api_key=api_key,
                                                        template=template,
                                                        reply_to_text=reply_to_text)

    postcode = letter_data['personalisation']['postcode']
    if not is_a_real_uk_postcode(postcode):
        raise ValidationError(message='A real UK postcode is required.')

    test_key = api_key.key_type == KEY_TYPE_TEST

    # if we don't want to actually send the letter, then start it off in SENDING so we don't pick it up
    status = NOTIFICATION_CREATED if not test_key else NOTIFICATION_SENDING
    queue = QueueNames.CREATE_LETTERS_PDF if not test_key else QueueNames.RESEARCH_MODE

    letter_data['personalisation']['postcode'] = format_postcode_for_printing(postcode)

    notification = create_letter_notification(letter_data=letter_data,
                                              template=template,
                                              api_key=api_key,
                                              status=status,
                                              reply_to_text=reply_to_text)

    create_letters_pdf.apply_async(
        [str(notification.id)],
        queue=queue
    )

    if test_key:
        if current_app.config['NOTIFY_ENVIRONMENT'] in ['preview', 'development']:
            create_fake_letter_response_file.apply_async(
                (notification.reference,),
                queue=queue
            )
        else:
            update_notification_status_by_reference(notification.reference, NOTIFICATION_DELIVERED)

    return notification


def process_precompiled_letter_notifications(*, letter_data, api_key, template, reply_to_text):
    try:
        status = NOTIFICATION_PENDING_VIRUS_CHECK
        letter_content = base64.b64decode(letter_data['content'])
    except ValueError:
        raise BadRequestError(message='Cannot decode letter content (invalid base64 encoding)', status_code=400)

    notification = create_letter_notification(letter_data=letter_data,
                                              template=template,
                                              api_key=api_key,
                                              status=status,
                                              reply_to_text=reply_to_text)

    filename = upload_letter_pdf(notification, letter_content, precompiled=True)

    current_app.logger.info('Calling task scan-file for {}'.format(filename))

    # call task to add the filename to anti virus queue
    if current_app.config['ANTIVIRUS_ENABLED']:
        notify_celery.send_task(
            name=TaskNames.SCAN_FILE,
            kwargs={'filename': filename},
            queue=QueueNames.ANTIVIRUS,
        )
    else:
        # stub out antivirus in dev
        process_virus_scan_passed.apply_async(
            kwargs={'filename': filename},
            queue=QueueNames.LETTERS,
        )

    return notification


def get_reply_to_text(notification_type, form, template):
    reply_to = None
    if notification_type == EMAIL_TYPE:
        service_email_reply_to_id = form.get("email_reply_to_id", None)
        reply_to = check_service_email_reply_to_id(
            str(authenticated_service.id), service_email_reply_to_id, notification_type
        ) or template.get_reply_to_text()

    elif notification_type == SMS_TYPE:
        service_sms_sender_id = form.get("sms_sender_id", None)
        sms_sender_id = check_service_sms_sender_id(
            str(authenticated_service.id), service_sms_sender_id, notification_type
        )
        if sms_sender_id:
            reply_to = try_validate_and_format_phone_number(sms_sender_id)
        else:
            reply_to = template.get_reply_to_text()

    elif notification_type == LETTER_TYPE:
        reply_to = template.get_reply_to_text()

    return reply_to
