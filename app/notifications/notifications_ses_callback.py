from datetime import datetime

from flask import (
    current_app,
    json
)

from app import statsd_client
from app.clients.email.aws_ses import get_aws_responses
from app.dao import (
    notifications_dao
)
from app.dao.complaint_dao import save_complaint
from app.dao.notifications_dao import dao_get_notification_history_by_reference
from app.dao.service_callback_api_dao import (
    get_service_delivery_status_callback_api_for_service, get_service_complaint_callback_api_for_service
)
from app.models import Complaint
from app.notifications.process_client_response import validate_callback_data
from app.celery.service_callback_tasks import (
    send_delivery_status_to_service,
    send_complaint_to_service,
    create_delivery_status_callback_data,
    create_complaint_callback_data
)
from app.config import QueueNames


def process_ses_response(ses_request):
    client_name = 'SES'
    try:
        errors = validate_callback_data(data=ses_request, fields=['Message'], client_name=client_name)
        if errors:
            return errors

        ses_message = json.loads(ses_request['Message'])
        errors = validate_callback_data(data=ses_message, fields=['notificationType'], client_name=client_name)
        if errors:
            return errors

        notification_type = ses_message['notificationType']
        if notification_type == 'Bounce':
            notification_type = determine_notification_bounce_type(notification_type, ses_message)
        elif notification_type == 'Complaint':
            complaint, notification, recipient = handle_complaint(ses_message)
            _check_and_queue_complaint_callback_task(complaint, notification, recipient)
            return

        try:
            aws_response_dict = get_aws_responses(notification_type)
        except KeyError:
            error = "{} callback failed: status {} not found".format(client_name, notification_type)
            return error

        notification_status = aws_response_dict['notification_status']

        try:
            reference = ses_message['mail']['messageId']
            notification = notifications_dao.update_notification_status_by_reference(
                reference,
                notification_status
            )
            if not notification:
                return

            if not aws_response_dict['success']:
                current_app.logger.info(
                    "SES delivery failed: notification id {} and reference {} has error found. Status {}".format(
                        notification.id,
                        reference,
                        aws_response_dict['message']
                    )
                )
            else:
                current_app.logger.info('{} callback return status of {} for notification: {}'.format(
                    client_name,
                    notification_status,
                    notification.id))
            statsd_client.incr('callback.ses.{}'.format(notification_status))
            if notification.sent_at:
                statsd_client.timing_with_dates(
                    'callback.ses.elapsed-time'.format(client_name.lower()),
                    datetime.utcnow(),
                    notification.sent_at
                )

            _check_and_queue_callback_task(notification)
            return

        except KeyError:
            error = "SES callback failed: messageId missing"
            return error

    except ValueError:
        error = "{} callback failed: invalid json".format(client_name)
        return error


def determine_notification_bounce_type(notification_type, ses_message):
    remove_emails_from_bounce(ses_message)
    current_app.logger.info('SES bounce dict: {}'.format(ses_message))
    if ses_message['bounce']['bounceType'] == 'Permanent':
        notification_type = ses_message['bounce']['bounceType']  # permanent or not
    else:
        notification_type = 'Temporary'
    return notification_type


def handle_complaint(ses_message):
    recipient_email = remove_emails_from_complaint(ses_message)[0]
    current_app.logger.info("Complaint from SES: \n{}".format(ses_message))
    try:
        reference = ses_message['mail']['messageId']
    except KeyError as e:
        current_app.logger.exception("Complaint from SES failed to get reference from message", e)
        return
    notification = dao_get_notification_history_by_reference(reference)
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
    service_callback_api = get_service_delivery_status_callback_api_for_service(service_id=notification.service_id)
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
