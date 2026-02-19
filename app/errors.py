from typing import Any

from flask import Blueprint, current_app, json, jsonify
from flask.typing import ResponseReturnValue
from jsonschema import ValidationError as JsonSchemaValidationError
from marshmallow import ValidationError
from notifications_utils.eventlet import EventletTimeout
from notifications_utils.recipient_validation.errors import InvalidRecipientError
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound
from werkzeug.exceptions import HTTPException

from app.authentication.auth import AuthError
from app.exceptions import ArchiveValidationError
from app.load_shedding import ServiceUnavailableError


class VirusScanError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class InvalidRequest(Exception):
    code = None
    fields: list[dict] = []

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__()
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {"result": "error", "message": self.message}

    def to_dict_v2(self) -> dict[str, Any]:
        """
        Version 2 of the public api error response.
        """
        return {
            "status_code": self.status_code,
            "errors": [{"error": self.__class__.__name__, "message": self.message}],
        }

    def __str__(self) -> str:
        return f"InvalidRequest: status_code={self.status_code}; message={self.message}"


def register_errors(blueprint: Blueprint):  # noqa: C901
    @blueprint.errorhandler(InvalidRecipientError)
    def invalid_format(error: InvalidRecipientError) -> ResponseReturnValue:
        return jsonify(result="error", message=str(error)), 400

    @blueprint.errorhandler(AuthError)
    def authentication_error(error: AuthError) -> ResponseReturnValue:
        return jsonify(result="error", message=error.message), error.code

    @blueprint.errorhandler(ServiceUnavailableError)
    def service_unavailable_error(error: ServiceUnavailableError) -> ResponseReturnValue:
        response = jsonify(result="error", message=error.message)
        response.status_code = 429
        response.headers["Retry-After"] = str(error.retry_after)
        current_app.logger.info(error)
        return response

    @blueprint.errorhandler(ValidationError)
    def marshmallow_validation_error(error: ValidationError) -> ResponseReturnValue:
        current_app.logger.info(error)
        return jsonify(result="error", message=error.messages), 400

    @blueprint.errorhandler(JsonSchemaValidationError)
    def jsonschema_validation_error(error: JsonSchemaValidationError) -> ResponseReturnValue:
        current_app.logger.info(error)
        return jsonify(json.loads(error.message)), 400

    @blueprint.errorhandler(ArchiveValidationError)
    def archive_validation_error(error: ArchiveValidationError) -> ResponseReturnValue:
        current_app.logger.info(error)
        return jsonify(result="error", message=str(error)), 400

    @blueprint.errorhandler(InvalidRequest)
    def invalid_data(error: InvalidRequest) -> ResponseReturnValue:
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        current_app.logger.info(error)
        return response

    @blueprint.errorhandler(400)
    def bad_request(e: HTTPException) -> ResponseReturnValue:
        msg = e.description or "Invalid request parameters"
        current_app.logger.exception(msg)
        return jsonify(result="error", message=str(msg)), 400

    @blueprint.errorhandler(401)
    def unauthorized(e: HTTPException) -> ResponseReturnValue:
        error_message = "Unauthorized: authentication token must be provided"
        return jsonify(result="error", message=error_message), 401, [("WWW-Authenticate", "Bearer")]

    @blueprint.errorhandler(403)
    def forbidden(e: HTTPException) -> ResponseReturnValue:
        error_message = "Forbidden: invalid authentication token provided"
        return jsonify(result="error", message=error_message), 403

    @blueprint.errorhandler(429)
    def limit_exceeded(e: HTTPException) -> ResponseReturnValue:
        current_app.logger.exception(e)
        return jsonify(result="error", message=str(e.description)), 429

    @blueprint.errorhandler(NoResultFound)
    @blueprint.errorhandler(DataError)
    def no_result_found(e: NoResultFound | DataError) -> ResponseReturnValue:
        current_app.logger.info(e, exc_info=True)
        return jsonify(result="error", message="No result found"), 404

    @blueprint.errorhandler(EventletTimeout)
    def eventlet_timeout(error: EventletTimeout) -> ResponseReturnValue:
        current_app.logger.exception(error)
        return jsonify(result="error", message="Timeout serving request"), 504

    # this must be defined after all other error handlers since it catches the generic Exception object
    @blueprint.app_errorhandler(500)
    @blueprint.errorhandler(Exception)
    def internal_server_error(e: Exception | HTTPException) -> ResponseReturnValue:
        # if e is a werkzeug InternalServerError then it may wrap the original exception. For more details see:
        # https://flask.palletsprojects.com/en/1.1.x/errorhandling/?highlight=internalservererror#unhandled-exceptions
        e = getattr(e, "original_exception", e)
        current_app.logger.exception(e)
        return jsonify(result="error", message="Internal server error"), 500
