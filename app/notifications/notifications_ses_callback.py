from flask import current_app

from app.dao.complaint_dao import save_complaint
from app.dao.notifications_dao import dao_get_notification_or_history_by_reference
from app.dao.service_callback_api_dao import (
    get_service_delivery_status_callback_api_for_service, get_service_complaint_callback_api_for_service
)
from app.models import Complaint
from app.celery.service_callback_tasks import (
    send_delivery_status_to_service,
    send_complaint_to_service,
    create_delivery_status_callback_data,
    create_complaint_callback_data
)
from app.config import QueueNames


def determine_notification_bounce_type(notification_type, ses_message):
    remove_emails_from_bounce(ses_message)
    if ses_message['bounce']['bounceType'] == 'Permanent':
        notification_type = ses_message['bounce']['bounceType']  # permanent or not
    else:
        notification_type = 'Temporary'
    return notification_type, ses_message


def handle_complaint(ses_message):
    recipient_email = remove_emails_from_complaint(ses_message)[0]
    current_app.logger.info("Complaint from SES: \n{}".format(ses_message))
    try:
        reference = ses_message['mail']['messageId']
    except KeyError as e:
        current_app.logger.exception("Complaint from SES failed to get reference from message", e)
        return
    notification = dao_get_notification_or_history_by_reference(reference)
    ses_complaint = ses_message.get('complaint', None)

    complaint = Complaint(
        notification_id=notification.id,
        service_id=notification.service_id,
        ses_feedback_id=ses_complaint.get('feedbackId', None) if ses_complaint else None,
        complaint_type=ses_complaint.get('complaintFeedbackType', None) if ses_complaint else None,
        complaint_date=ses_complaint.get('timestamp', None) if ses_complaint else None
    )
    save_complaint(complaint)
    return complaint, notification, recipient_email


def remove_mail_headers(dict_to_edit):
    if dict_to_edit['mail'].get('headers'):
        dict_to_edit['mail'].pop('headers')
    if dict_to_edit['mail'].get('commonHeaders'):
        dict_to_edit['mail'].pop('commonHeaders')


def remove_emails_from_bounce(bounce_dict):
    remove_mail_headers(bounce_dict)
    bounce_dict['mail'].pop('destination')
    bounce_dict['bounce'].pop('bouncedRecipients')


def remove_emails_from_complaint(complaint_dict):
    remove_mail_headers(complaint_dict)
    complaint_dict['complaint'].pop('complainedRecipients')
    return complaint_dict['mail'].pop('destination')


def _check_and_queue_callback_task(notification):
    # queue callback task only if the service_callback_api exists
    service_callback_api = SerialisedServiceCallbackApi.from_service_id(service_id)
    if service_callback_api:
        notification_data = create_delivery_status_callback_data(notification, service_callback_api)
        send_delivery_status_to_service.apply_async([str(notification.id), notification_data],
                                                    queue=QueueNames.CALLBACKS)


def _check_and_queue_complaint_callback_task(complaint, notification, recipient):
    # queue callback task only if the service_callback_api exists
    service_callback_api = get_service_complaint_callback_api_for_service(service_id=notification.service_id)
    if service_callback_api:
        complaint_data = create_complaint_callback_data(complaint, notification, service_callback_api, recipient)
        send_complaint_to_service.apply_async([complaint_data], queue=QueueNames.CALLBACKS)
