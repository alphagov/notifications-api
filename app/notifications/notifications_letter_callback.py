import json

from functools import wraps

from flask import (
    Blueprint,
    jsonify,
    request,
    current_app
)

from app.celery.tasks import update_letter_notifications_statuses
from app.v2.errors import register_errors
from app.notifications.utils import autoconfirm_subscription
from app.schema_validation import validate
from app.celery import QueueNames

letter_callback_blueprint = Blueprint('notifications_letter_callback', __name__)
register_errors(letter_callback_blueprint)


dvla_sns_callback_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "sns callback received on s3 update",
    "type": "object",
    "title": "dvla internal sns callback",
    "properties": {
        "Type": {"enum": ["Notification", "SubscriptionConfirmation"]},
        "MessageId": {"type": "string"},
        "Message": {"type": ["string", "object"]}
    },
    "required": ["Type", "MessageId", "Message"]
}


def validate_schema(schema):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kw):
            validate(request.get_json(force=True), schema)
            return f(*args, **kw)
        return wrapper
    return decorator


@letter_callback_blueprint.route('/notifications/letter/dvla', methods=['POST'])
@validate_schema(dvla_sns_callback_schema)
def process_letter_response():
    req_json = request.get_json(force=True)
    current_app.logger.info('Received SNS callback: {}'.format(req_json))
    if not autoconfirm_subscription(req_json):
        # The callback should have one record for an S3 Put Event.
        message = json.loads(req_json['Message'])
        filename = message['Records'][0]['s3']['object']['key']
        current_app.logger.info('Received file from DVLA: {}'.format(filename))
        current_app.logger.info('DVLA callback: Calling task to update letter notifications')
        update_letter_notifications_statuses.apply_async([filename], queue=QueueNames.NOTIFY)

    return jsonify(
        result="success", message="DVLA callback succeeded"
    ), 200
