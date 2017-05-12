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

letter_callback_blueprint = Blueprint('notifications_letter_callback', __name__)

from app.errors import (
    register_errors,
    InvalidRequest
)

register_errors(letter_callback_blueprint)


@letter_callback_blueprint.route('/notifications/letter/dvla', methods=['POST'])
def process_letter_response():
    try:
        dvla_request = json.loads(request.data)
        current_app.logger.info(dvla_request)
        return jsonify(
            result="success", message="DVLA callback succeeded"
        ), 200
    except ValueError:
        error = "DVLA callback failed: invalid json"
        raise InvalidRequest(error, status_code=400)
