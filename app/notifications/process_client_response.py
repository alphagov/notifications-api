import uuid

from datetime import datetime
from flask import current_app

from app import statsd_client
from app.dao import notifications_dao
from app.clients.sms.firetext import get_firetext_responses
from app.clients.sms.mmg import get_mmg_responses
from app.celery.statistics_tasks import create_outcome_notification_statistic_tasks


sms_response_mapper = {
    'MMG': get_mmg_responses,
    'Firetext': get_firetext_responses
}


def validate_callback_data(data, fields, client_name):
    errors = []
    for f in fields:
        if not str(data.get(f, '')):
            error = "{} callback failed: {} missing".format(client_name, f)
            errors.append(error)
    return errors if len(errors) > 0 else None


def process_sms_client_response(status, reference, client_name):
    success = None
    errors = None
    # validate reference
    if reference == 'send-sms-code':
        success = "{} callback succeeded: send-sms-code".format(client_name)
        return success, errors

    try:
        uuid.UUID(reference, version=4)
    except ValueError:
        message = "{} callback with invalid reference {}".format(client_name, reference)
        return success, message

    try:
        response_parser = sms_response_mapper[client_name]
    except KeyError:
        return success, 'unknown sms client: {}'.format(client_name)

    # validate  status
    try:
        response_dict = response_parser(status)
        current_app.logger.info('{} callback return status of {} for reference: {}'.format(
            client_name, status, reference)
        )
    except KeyError:
        msg = "{} callback failed: status {} not found.".format(client_name, status)
        return success, msg

    notification_status = response_dict['notification_status']
    notification_status_message = response_dict['message']
    notification_success = response_dict['success']

    # record stats
    notification = notifications_dao.update_notification_status_by_id(reference, notification_status)
    if not notification:
        current_app.logger.warning("{} callback failed: notification {} either not found or already updated "
                                   "from sending. Status {}".format(client_name,
                                                                    reference,
                                                                    notification_status_message))
        return success, errors

    if not notification_success:
        current_app.logger.info(
            "{} delivery failed: notification {} has error found. Status {}".format(client_name,
                                                                                    reference,
                                                                                    notification_status_message))

    statsd_client.incr('callback.{}.{}'.format(client_name.lower(), notification_status))
    if notification.sent_at:
        statsd_client.timing_with_dates(
            'callback.{}.elapsed-time'.format(client_name.lower()),
            datetime.utcnow(),
            notification.sent_at
        )

    create_outcome_notification_statistic_tasks(notification)

    success = "{} callback succeeded. reference {} updated".format(client_name, reference)
    return success, errors
