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

from app.notifications.process_client_response import validate_callback_data

ses_callback_blueprint = Blueprint('notifications_ses_callback', __name__)

from app.errors import (
    register_errors,
    InvalidRequest
)
register_errors(ses_callback_blueprint)


@ses_callback_blueprint.route('/notifications/email/ses', methods=['POST'])
def process_ses_response():
    client_name = 'SES'
    try:
        ses_request = json.loads(request.data)

        if 'Type' in ses_request and ses_request['Type'] == 'SubscriptionConfirmation':
            current_app.logger.info("SNS subscription confirmation url: {}".format(ses_request['SubscribeURL']))

        errors = validate_callback_data(data=ses_request, fields=['Message'], client_name=client_name)
        if errors:
            raise InvalidRequest(errors, status_code=400)

        ses_message = json.loads(ses_request['Message'])
        errors = validate_callback_data(data=ses_message, fields=['notificationType'], client_name=client_name)
        if errors:
            raise InvalidRequest(errors, status_code=400)

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
            raise InvalidRequest(error, status_code=400)

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
                raise InvalidRequest(error, status_code=404)

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
            return jsonify(
                result="success", message="SES callback succeeded"
            ), 200

        except KeyError:
            message = "SES callback failed: messageId missing"
            raise InvalidRequest(message, status_code=400)

    except ValueError as ex:
        error = "{} callback failed: invalid json".format(client_name)
        raise InvalidRequest(error, status_code=400)
