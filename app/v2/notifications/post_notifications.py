import base64
import functools
import uuid
from datetime import datetime

from boto.exception import SQSError
from flask import request, jsonify, current_app, abort
from notifications_utils.postal_address import PostalAddress
from notifications_utils.recipients import try_validate_and_format_phone_number
from gds_metrics import Histogram

from app import (
    api_user,
    authenticated_service,
    notify_celery,
    document_download_client,
    encryption,
    DATETIME_FORMAT
)
from app.celery.letters_pdf_tasks import get_pdf_for_templated_letter, sanitise_letter
from app.celery.research_mode_tasks import create_fake_letter_response_file
from app.celery.tasks import save_api_email
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
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    KEY_TYPE_TEAM,
    NOTIFICATION_CREATED,
    NOTIFICATION_SENDING,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING_VIRUS_CHECK,
    INTERNATIONAL_LETTERS,
    Notification)
from app.notifications.process_letter_notifications import (
    create_letter_notification
)
from app.notifications.process_notifications import (
    persist_notification,
    persist_scheduled_notification,
    send_notification_to_queue,
    simulated_recipient,
    send_notification_to_queue_detached)
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
    create_post_letter_response_from_notification,
    create_post_sms_response_from_notification_detached, create_post_email_response_from_notification_detached,
    create_post_letter_response_from_notification_detached)
from app.v2.notifications.notification_schemas import (
    post_sms_request,
    post_email_request,
    post_letter_request,
    post_precompiled_letter_request
)
from app.v2.utils import get_valid_json


POST_NOTIFICATION_JSON_PARSE_DURATION_SECONDS = Histogram(
    'post_notification_json_parse_duration_seconds',
    'Time taken to parse and validate post request json',
)


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
    with POST_NOTIFICATION_JSON_PARSE_DURATION_SECONDS.time():
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
            template=template_with_content,
            template_process_type=template.process_type,
            service=authenticated_service,
            reply_to_text=reply_to
        )

    return jsonify(notification), 201


def create_response_for_post_notification(notification_id, client_reference, template_id, template_version, service_id,
                                          notification_type, reply_to, scheduled_for,
                                          template_with_content):
    if notification_type == SMS_TYPE:
        create_resp_partial = functools.partial(
            create_post_sms_response_from_notification_detached,
            from_number=reply_to,
        )
    elif notification_type == EMAIL_TYPE:
        create_resp_partial = functools.partial(
            create_post_email_response_from_notification_detached,
            subject=template_with_content.subject,
            email_from='{}@{}'.format(authenticated_service.email_from, current_app.config['NOTIFY_EMAIL_DOMAIN']),
        )
    elif notification_type == LETTER_TYPE:
        create_resp_partial = functools.partial(
            create_post_letter_response_from_notification_detached,
            subject=template_with_content.subject,
        )
    resp = create_resp_partial(
        notification_id, client_reference, template_id, template_version, service_id, 
        url_root=request.url_root,
        scheduled_for=scheduled_for,
        content=template_with_content.content_with_placeholders_filled_in,
    )
    return resp


def process_sms_or_email_notification(
    *, form, notification_type, api_key, template, template_process_type, service, reply_to_text=None
):
    notification_id = uuid.uuid4()
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

    key_type = api_key.key_type
    service_in_research_mode = service.resear
    resp = create_response_for_post_notification(
        notification_id=notification_id,
        client_reference=form.get('reference', None),
        template_id=template.id,
        template_version=template._template['version'],
        service_id=service.id,
        notification_type=notification_type,
        reply_to=reply_to_text,
        scheduled_for=None,
        template_with_content=template)

    if str(service.id) in current_app.config.get('HIGH_VOLUME_SERVICE') and api_key.key_type == KEY_TYPE_NORMAL \
       and notification_type == EMAIL_TYPE:
        # Put GOV.UK Email notifications onto a queue
        # To take the pressure off the db for API requests put the notification for our high volume service onto a queue
        # the task will then save the notification, then call send_notification_to_queue.
        # We know that this team does not use the GET request, but relies on callbacks to get the status updates.
        try:
            notification = save_email_to_queue(
                form=form,
                notification_id=str(notification_id),
                notification_type=notification_type,
                api_key=api_key,
                template=template,
                service_id=service.id,
                personalisation=personalisation,
                document_download_count=document_download_count,
                reply_to_text=reply_to_text
            )
            return notification
        except SQSError:
            # if SQS cannot put the task on the queue, it's probably because the notification body was too long and it
            # went over SQS's 256kb message limit. If so, we
            current_app.logger.info(
                f'Notification {notification_id} failed to save to high volume queue. Using normal flow instead'
            )

    persist_notification(
        notification_id=notification_id,
        template_id=template.id,
        template_version=template._template['version'],
        recipient=form_send_to,
        service=service,
        personalisation=personalisation,
        notification_type=notification_type,
        api_key_id=api_key.id,
        key_type=key_type,
        client_reference=form.get('reference', None),
        simulated=simulated,
        reply_to_text=reply_to_text,
        document_download_count=document_download_count
    )

    scheduled_for = form.get("scheduled_for", None)
    if scheduled_for:
        persist_scheduled_notification(notification_id, form["scheduled_for"])
    else:
        if not simulated:
            queue_name = QueueNames.PRIORITY if template_process_type == PRIORITY else None
            send_notification_to_queue_detached(
                key_type=key_type,
                notification_type=notification_type,
                notification_id=notification_id,
                research_mode=False,  # research_mode is a deprecated mode
                queue=queue_name
            )
        else:
            current_app.logger.debug("POST simulated notification for id: {}".format(notification_id))

    return resp


def save_email_to_queue(
    *,
    notification_id,
    form,
    notification_type,
    api_key,
    template,
    service_id,
    personalisation,
    document_download_count,
    reply_to_text=None
):
    data = {
        "id": notification_id,
        "template_id": str(template.id),
        "template_version": template.version,
        "to": form['email_address'],
        "service_id": str(service_id),
        "personalisation": personalisation,
        "notification_type": notification_type,
        "api_key_id": str(api_key.id),
        "key_type": api_key.key_type,
        "client_reference": form.get('reference', None),
        "reply_to_text": reply_to_text,
        "document_download_count": document_download_count,
        "status": NOTIFICATION_CREATED,
        "created_at": datetime.utcnow().strftime(DATETIME_FORMAT),
    }
    encrypted = encryption.encrypt(
        data
    )

    save_api_email.apply_async([encrypted], queue=QueueNames.SAVE_API_EMAIL)
    return Notification(**data)


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
                    service.id, personalisation_data[key]['file'], personalisation_data[key].get('is_csv')
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

    address = PostalAddress.from_personalisation(
        letter_data['personalisation'],
        allow_international_letters=api_key.service.has_permission(INTERNATIONAL_LETTERS),
    )

    if not address.has_enough_lines:
        raise ValidationError(
            message=f'Address must be at least {PostalAddress.MIN_LINES} lines'
        )

    if address.has_too_many_lines:
        raise ValidationError(
            message=f'Address must be no more than {PostalAddress.MAX_LINES} lines'
        )

    if not address.has_valid_last_line:
        if address.allow_international_letters:
            raise ValidationError(
                message=f'Last line of address must be a real UK postcode or another country'
            )
        raise ValidationError(
            message='Must be a real UK postcode'
        )

    test_key = api_key.key_type == KEY_TYPE_TEST

    # if we don't want to actually send the letter, then start it off in SENDING so we don't pick it up
    status = NOTIFICATION_CREATED if not test_key else NOTIFICATION_SENDING
    queue = QueueNames.CREATE_LETTERS_PDF if not test_key else QueueNames.RESEARCH_MODE

    notification = create_letter_notification(letter_data=letter_data,
                                              template=template,
                                              api_key=api_key,
                                              status=status,
                                              reply_to_text=reply_to_text)

    get_pdf_for_templated_letter.apply_async(
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
        sanitise_letter.apply_async(
            [filename],
            queue=QueueNames.LETTERS
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
