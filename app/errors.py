from flask import (
    jsonify,
    current_app
)
from sqlalchemy.exc import SQLAlchemyError, DataError
from sqlalchemy.orm.exc import NoResultFound
from marshmallow import ValidationError
from app.authentication.auth import AuthError


class InvalidRequest(Exception):

    def __init__(self, message, status_code):
        super().__init__()
        self.message = message
        self.status_code = status_code

    def to_dict(self):
        return {'result': 'error', 'message': self.message}

    def __str__(self):
        return str(self.to_dict())


def register_errors(blueprint):

    @blueprint.app_errorhandler(AuthError)
    def authentication_error(error):
        return jsonify(result='error', message=error.message), error.code

    @blueprint.app_errorhandler(ValidationError)
    def validation_error(error):
        current_app.logger.error(error)
        return jsonify(result='error', message=error.messages), 400

    @blueprint.app_errorhandler(InvalidRequest)
    def invalid_data(error):
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        current_app.logger.error(error)
        return response

    @blueprint.app_errorhandler(400)
    def bad_request(e):
        msg = e.description or "Invalid request parameters"
        current_app.logger.exception(msg)
        return jsonify(result='error', message=str(msg)), 400

    @blueprint.app_errorhandler(401)
    def unauthorized(e):
        error_message = "Unauthorized, authentication token must be provided"
        return jsonify(result='error', message=error_message), 401, [('WWW-Authenticate', 'Bearer')]

    @blueprint.app_errorhandler(403)
    def forbidden(e):
        error_message = "Forbidden, invalid authentication token provided"
        return jsonify(result='error', message=error_message), 403

    @blueprint.app_errorhandler(404)
    def page_not_found(e):
        msg = e.description or "Not found"
        current_app.logger.exception(msg)
        return jsonify(result='error', message=msg), 404

    @blueprint.app_errorhandler(429)
    def limit_exceeded(e):
        current_app.logger.exception(e)
        return jsonify(result='error', message=str(e.description)), 429

    @blueprint.app_errorhandler(NoResultFound)
    @blueprint.app_errorhandler(DataError)
    def no_result_found(e):
        current_app.logger.exception(e)
        return jsonify(result='error', message="No result found"), 404

    @blueprint.app_errorhandler(SQLAlchemyError)
    def db_error(e):
        current_app.logger.exception(e)
        if e.orig.pgerror and \
            ('duplicate key value violates unique constraint "services_name_key"' in e.orig.pgerror or
                'duplicate key value violates unique constraint "services_email_from_key"' in e.orig.pgerror):
            return jsonify(
                result='error',
                message={'name': ["Duplicate service name '{}'".format(
                    e.params.get('name', e.params.get('email_from', ''))
                )]}
            ), 400
        return jsonify(result='error', message="Internal server error"), 500

    # this must be defined after all other error handlers since it catches the generic Exception object
    @blueprint.app_errorhandler(500)
    @blueprint.app_errorhandler(Exception)
    def internal_server_error(e):
        current_app.logger.exception(e)
        return jsonify(result='error', message="Internal server error"), 500
