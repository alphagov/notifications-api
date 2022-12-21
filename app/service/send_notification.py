import urllib

from flask import current_app
from notifications_utils.s3 import S3ObjectNotFound
from notifications_utils.s3 import s3download as utils_s3download
from sqlalchemy.orm.exc import NoResultFound

from app import create_random_identifier
from app.config import QueueNames
from app.dao.notifications_dao import (
    _update_notification_status,
    get_notification_by_id,
)
from app.dao.service_email_reply_to_dao import dao_get_reply_to_by_id
from app.dao.service_sms_sender_dao import dao_get_service_sms_senders_by_id
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import (
    dao_get_template_by_id_and_service_id,
    get_precompiled_letter_template,
)
from app.dao.users_dao import get_user_by_id
from app.letters.utils import (
    generate_letter_pdf_filename,
    get_billable_units_for_letter_page_count,
    get_page_count,
    move_uploaded_pdf_to_letters_bucket,
)
from app.models import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    NOTIFICATION_DELIVERED,
    PRIORITY,
    SMS_TYPE,
)
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
)
from app.notifications.validators import (
    check_service_has_permission,
    check_service_over_daily_message_limit,
    validate_address,
    validate_and_format_recipient,
    validate_template,
)
from app.v2.errors import BadRequestError


def validate_created_by(service, created_by_id):
    user = get_user_by_id(created_by_id)
    if service not in user.services:
        message = 'Can’t create notification - {} is not part of the "{}" service'.format(user.name, service.name)
        raise BadRequestError(message=message)


def create_one_off_reference(template_type):
    if template_type == LETTER_TYPE:
        return create_random_identifier()
    return None


def _get_reference_from_personalisation(personalisation):
    if personalisation:
        return personalisation.get("reference")
    return None


def send_one_off_notification(service_id, post_data):
    service = dao_fetch_service_by_id(service_id)
    template = dao_get_template_by_id_and_service_id(template_id=post_data["template_id"], service_id=service_id)

    personalisation = post_data.get("personalisation", None)

    validate_template(template.id, personalisation, service, template.template_type)

    check_service_over_daily_message_limit(service, KEY_TYPE_NORMAL, notification_type=None)

    validate_and_format_recipient(
        send_to=post_data["to"],
        key_type=KEY_TYPE_NORMAL,
        service=service,
        notification_type=template.template_type,
        allow_guest_list_recipients=False,
    )
    postage = None
    client_reference = None
    if template.template_type == LETTER_TYPE:
        # Validate address and set postage to europe|rest-of-world if international letter,
        # otherwise persist_notification with use template postage
        postage = validate_address(service, personalisation)
        if not postage:
            postage = template.postage

        client_reference = _get_reference_from_personalisation(personalisation)

    validate_created_by(service, post_data["created_by"])

    sender_id = post_data.get("sender_id", None)
    reply_to = get_reply_to_text(
        notification_type=template.template_type, sender_id=sender_id, service=service, template=template
    )
    notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=post_data["to"],
        service=service,
        personalisation=personalisation,
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        created_by_id=post_data["created_by"],
        reply_to_text=reply_to,
        reference=create_one_off_reference(template.template_type),
        postage=postage,
        client_reference=client_reference,
    )

    queue_name = QueueNames.PRIORITY if template.process_type == PRIORITY else None

    if template.template_type == LETTER_TYPE and service.research_mode:
        _update_notification_status(
            notification,
            NOTIFICATION_DELIVERED,
        )
    else:
        send_notification_to_queue(
            notification=notification,
            research_mode=service.research_mode,
            queue=queue_name,
        )

    return {"id": str(notification.id)}


def get_reply_to_text(notification_type, sender_id, service, template):
    reply_to = None
    if sender_id:
        try:
            if notification_type == EMAIL_TYPE:
                message = "Reply to email address not found"
                reply_to = dao_get_reply_to_by_id(service.id, sender_id).email_address
            elif notification_type == SMS_TYPE:
                message = "SMS sender not found"
                reply_to = dao_get_service_sms_senders_by_id(service.id, sender_id).get_reply_to_text()
        except NoResultFound:
            raise BadRequestError(message=message)
    else:
        reply_to = template.get_reply_to_text()
    return reply_to


def send_pdf_letter_notification(service_id, post_data):
    service = dao_fetch_service_by_id(service_id)

    check_service_has_permission(LETTER_TYPE, [p.permission for p in service.permissions])
    check_service_over_daily_message_limit(service, KEY_TYPE_NORMAL, notification_type=None)
    validate_created_by(service, post_data["created_by"])
    validate_and_format_recipient(
        send_to=post_data["recipient_address"],
        key_type=KEY_TYPE_NORMAL,
        service=service,
        notification_type=LETTER_TYPE,
        allow_guest_list_recipients=False,
    )

    # notification already exists e.g. if the user clicked send in different tabs
    if get_notification_by_id(post_data["file_id"]):
        return {"id": str(post_data["file_id"])}

    template = get_precompiled_letter_template(service.id)
    file_location = "service-{}/{}.pdf".format(service.id, post_data["file_id"])

    try:
        letter = utils_s3download(current_app.config["TRANSIENT_UPLOADED_LETTERS"], file_location)
    except S3ObjectNotFound as e:
        current_app.logger.warning(
            "Letter {}.pdf not in transient {} bucket".format(
                post_data["file_id"], current_app.config["TRANSIENT_UPLOADED_LETTERS"]
            )
        )

        raise e

    # Getting the page count won't raise an error since admin has already checked the PDF is valid
    page_count = get_page_count(letter.read())
    billable_units = get_billable_units_for_letter_page_count(page_count)

    personalisation = {"address_line_1": post_data["filename"]}

    notification = persist_notification(
        notification_id=post_data["file_id"],
        template_id=template.id,
        template_version=template.version,
        recipient=urllib.parse.unquote(post_data["recipient_address"]),
        service=service,
        personalisation=personalisation,
        notification_type=LETTER_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reference=create_one_off_reference(LETTER_TYPE),
        client_reference=post_data["filename"],
        created_by_id=post_data["created_by"],
        billable_units=billable_units,
        postage=post_data["postage"] or template.postage,
    )

    upload_filename = generate_letter_pdf_filename(
        reference=notification.reference,
        created_at=notification.created_at,
        ignore_folder=False,
        postage=notification.postage,
    )

    move_uploaded_pdf_to_letters_bucket(file_location, upload_filename)

    return {"id": str(notification.id)}
