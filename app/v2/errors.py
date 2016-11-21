import json
from flask import jsonify, current_app
from jsonschema import ValidationError
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound
from app.authentication.auth import AuthError
from app.errors import InvalidRequest
from app.notifications import SendNotificationToQueueError


class TooManyRequestsError(InvalidRequest):
    status_code = 429
    message_template = 'Exceeded send limits ({}) for today'

    def __init__(self, sending_limit):
        self.message = self.message_template.format(sending_limit)


class BadRequestError(InvalidRequest):
    status_code = 400
    message = "An error occurred"

    def __init__(self, fields=[], message=None):
        self.fields = fields
        self.message = message if message else self.message


def register_errors(blueprint):
    @blueprint.errorhandler(InvalidRequest)
    def invalid_data(error):
        current_app.logger.error(error)
        response = jsonify(error.to_dict_v2()), error.status_code
        return response

    @blueprint.errorhandler(ValidationError)
    def validation_error(error):
        current_app.logger.exception(error)
        return jsonify(json.loads(error.message)), 400

    @blueprint.errorhandler(NoResultFound)
    @blueprint.errorhandler(DataError)
    def no_result_found(e):
        current_app.logger.exception(e)
        return jsonify(status_code=404,
                       errors=[{"error": e.__class__.__name__, "message": "No result found"}]), 404

    @blueprint.errorhandler(AuthError)
    def auth_error(error):
        return jsonify(error.to_dict_v2()), error.code

    @blueprint.errorhandler(SendNotificationToQueueError)
    def failed_to_create_notification(error):
        current_app.logger.exception(error)
        return jsonify(
            status_code=500,
            errors=[{"error": error.__class__.__name__, "message": error.message}]), 500

    @blueprint.errorhandler(Exception)
    def internal_server_error(error):
        current_app.logger.exception(error)
        return jsonify(status_code=500,
                       errors=[{"error": error.__class__.__name__, "message": 'Internal server error'}]), 500
