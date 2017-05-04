from datetime import datetime

from flask import (
    Blueprint,
    jsonify,
    request,
    current_app,
    json
)

from app import statsd_client
from app.celery.tasks import update_letter_notifications_statuses
from app.clients.email.aws_ses import get_aws_responses
from app.dao import (
    notifications_dao
)

from app.notifications.process_client_response import validate_callback_data

letter_callback_blueprint = Blueprint('notifications_letter_callback', __name__)

from app.errors import (
    register_errors,
    InvalidRequest
)

register_errors(letter_callback_blueprint)


@letter_callback_blueprint.route('/notifications/letter/dvla', methods=['POST'])
def process_letter_response():
    try:
        req_json = json.loads(request.data)
        # The callback should have one record for an S3 Put Event.
        filename = req_json['Message']['Records'][0]['s3']['object']['key']

    except (ValueError, KeyError):
        error = "DVLA callback failed: Invalid JSON"
        raise InvalidRequest(error, status_code=400)

    else:
        current_app.logger.info('DVLA callback: Calling task to update letter notifications')
        update_letter_notifications_statuses.apply_async([filename], queue='notify')

        return jsonify(
            result="success", message="DVLA callback succeeded"
        ), 200
