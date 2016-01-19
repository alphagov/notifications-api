from flask import (
    Blueprint,
    jsonify,
    request
)

from app import notify_alpha_client
import re

mobile_regex = re.compile("^\\+44[\\d]{10}$")

notifications = Blueprint('notifications', __name__)


@notifications.route('/', methods=['GET'])
def get_notifications():
    return jsonify(notify_alpha_client.fetch_notifications()), 200


@notifications.route('/sms', methods=['POST'])
def create_sms_notification():
    notification = request.get_json()['notification']

    errors = {}
    to_errors = validate_to(notification)
    message_errors = validate_message(notification)

    if to_errors:
        errors.update(to_errors)
    if message_errors:
        errors.update(message_errors)

    if errors:
        return jsonify(result="error", message=errors), 400

    return jsonify(notify_alpha_client.send_sms(mobile_number=notification['to'], message=notification['message'])), 200


@notifications.route('/email', methods=['POST'])
def create_email_notification():
    return jsonify(id=123)


def validate_to(json_body):
    errors = []

    if 'to' not in json_body:
        errors.append('required')
    else:
        if not mobile_regex.match(json_body['to']):
            errors.append('invalid phone number, must be of format +441234123123')
    if errors:
        return {
            "to": errors
        }
    return None


def validate_message(json_body):
    errors = []

    if 'message' not in json_body:
        errors.append('required')
    else:
        message_length = len(json_body['message'])
        if message_length < 1 or message_length > 160:
            errors.append('Invalid length. [1 - 160]')

    if errors:
        return {
            "message": errors
        }
    return None
