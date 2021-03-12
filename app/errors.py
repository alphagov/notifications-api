from flask import current_app, json, jsonify
from jsonschema import ValidationError as JsonSchemaValidationError
from marshmallow import ValidationError
from notifications_utils.recipients import InvalidEmailError
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound

from app.authentication.auth import AuthError
from app.exceptions import ArchiveValidationError


class VirusScanError(Exception):
    def __init__(self, message):

        super().__init__(message)


class InvalidRequest(Exception):
    code = None
    fields = []

    def __init__(self, message, status_code):
        super().__init__()
        self.message = message
        self.status_code = status_code

    def to_dict(self):
        return {'result': 'error', 'message': self.message}

    def to_dict_v2(self):
        '''
        Version 2 of the public api error response.
        '''
        return {
            "status_code": self.status_code,
            "errors": [
                {
                    "error": self.__class__.__name__,
                    "message": self.message
                }
            ]
        }

    def __str__(self):
        return str(self.to_dict())


def register_errors(blueprint):
    @blueprint.errorhandler(InvalidEmailError)
    def invalid_format(error):
        # Please not that InvalidEmailError is re-raised for InvalidEmail or InvalidPhone,
        # work should be done in the utils app to tidy up these errors.
        return jsonify(result='error', message=str(error)), 400

    @blueprint.errorhandler(AuthError)
    def authentication_error(error):
        return jsonify(result='error', message=error.message), error.code

    @blueprint.errorhandler(ValidationError)
    def marshmallow_validation_error(error):
        current_app.logger.info(error)
        return jsonify(result='error', message=error.messages), 400

    @blueprint.errorhandler(JsonSchemaValidationError)
    def jsonschema_validation_error(error):
        current_app.logger.info(error)
        return jsonify(json.loads(error.message)), 400

    @blueprint.errorhandler(ArchiveValidationError)
    def archive_validation_error(error):
        current_app.logger.info(error)
        return jsonify(result='error', message=str(error)), 400

    @blueprint.errorhandler(InvalidRequest)
    def invalid_data(error):
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        current_app.logger.info(error)
        return response

    @blueprint.errorhandler(400)
    def bad_request(e):
        msg = e.description or "Invalid request parameters"
        current_app.logger.exception(msg)
        return jsonify(result='error', message=str(msg)), 400

    @blueprint.errorhandler(401)
    def unauthorized(e):
        error_message = "Unauthorized: authentication token must be provided"
        return jsonify(result='error', message=error_message), 401, [('WWW-Authenticate', 'Bearer')]

    @blueprint.errorhandler(403)
    def forbidden(e):
        error_message = "Forbidden: invalid authentication token provided"
        return jsonify(result='error', message=error_message), 403

    @blueprint.errorhandler(429)
    def limit_exceeded(e):
        current_app.logger.exception(e)
        return jsonify(result='error', message=str(e.description)), 429

    @blueprint.errorhandler(NoResultFound)
    @blueprint.errorhandler(DataError)
    def no_result_found(e):
        current_app.logger.info(e)
        return jsonify(result='error', message="No result found"), 404

    # this must be defined after all other error handlers since it catches the generic Exception object
    @blueprint.app_errorhandler(500)
    @blueprint.errorhandler(Exception)
    def internal_server_error(e):
        # if e is a werkzeug InternalServerError then it may wrap the original exception. For more details see:
        # https://flask.palletsprojects.com/en/1.1.x/errorhandling/?highlight=internalservererror#unhandled-exceptions
        e = getattr(e, 'original_exception', e)
        current_app.logger.exception(e)
        return jsonify(result='error', message="Internal server error"), 500
