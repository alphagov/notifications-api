from datetime import datetime

from flask import (
    Blueprint,
    jsonify,
    request,
    current_app,
    json
)

from app import statsd_client
from app.clients.email.aws_ses import get_aws_responses
from app.dao import (
    notifications_dao
)
from app.celery.statistics_tasks import create_outcome_notification_statistic_tasks
from app.notifications.process_client_response import validate_callback_data

ses_callback_blueprint = Blueprint('notifications_ses_callback', __name__)

from app.errors import (
    register_errors,
    InvalidRequest
)
register_errors(ses_callback_blueprint)


@ses_callback_blueprint.route('/notifications/email/ses', methods=['POST'])
def sns_callback_handler():
    errors, status, kwargs = process_ses_response(json.loads(request.data))
    if errors:
        raise InvalidRequest(errors, status)

    return jsonify(**kwargs), status


def process_ses_response(ses_request):
    client_name = 'SES'
    try:

        # TODO: remove this check once the sns_callback_handler is removed
        if not isinstance(ses_request, dict):
            ses_request = json.loads(ses_request)

        errors = validate_callback_data(data=ses_request, fields=['Message'], client_name=client_name)
        if errors:
            return errors, 400, {}

        ses_message = json.loads(ses_request['Message'])
        errors = validate_callback_data(data=ses_message, fields=['notificationType'], client_name=client_name)
        if errors:
            return errors, 400, {}

        notification_type = ses_message['notificationType']
        if notification_type == 'Bounce':
            if ses_message['bounce']['bounceType'] == 'Permanent':
                notification_type = ses_message['bounce']['bounceType']  # permanent or not
            else:
                notification_type = 'Temporary'
        try:
            aws_response_dict = get_aws_responses(notification_type)
        except KeyError:
            error = "{} callback failed: status {} not found".format(client_name, notification_type)
            return error, 400, {}

        notification_status = aws_response_dict['notification_status']

        try:
            reference = ses_message['mail']['messageId']
            notification = notifications_dao.update_notification_status_by_reference(
                reference,
                notification_status
            )
            if not notification:
                error = "SES callback failed: notification either not found or already updated " \
                        "from sending. Status {} for notification reference {}".format(notification_status, reference)
                return error, 404, {}

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

            create_outcome_notification_statistic_tasks(notification)

            return [], 200, {'result': "success", 'message': "SES callback succeeded"}

        except KeyError:
            error = "SES callback failed: messageId missing"
            return error, 400, {}

    except ValueError:
        error = "{} callback failed: invalid json".format(client_name)
        return error, 400, {}
