from flask import (
    jsonify,
    current_app
)
from sqlalchemy.exc import SQLAlchemyError, DataError
from sqlalchemy.orm.exc import NoResultFound


def register_errors(blueprint):

    @blueprint.app_errorhandler(400)
    def bad_request(e):
        return jsonify(result='error', message=str(e.description)), 400

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
        return jsonify(result='error', message=e.description or "Not found"), 404

    @blueprint.app_errorhandler(429)
    def limit_exceeded(e):
        return jsonify(result='error', message=str(e.description)), 429

    @blueprint.app_errorhandler(500)
    def internal_server_error(e):
        current_app.logger.exception(e)
        return jsonify(result='error', message="Internal server error"), 500

    @blueprint.app_errorhandler(NoResultFound)
    def no_result_found(e):
        current_app.logger.error(e)
        return jsonify(result='error', message="No result found"), 404

    @blueprint.app_errorhandler(DataError)
    def data_error(e):
        current_app.logger.error(e)
        return jsonify(result='error', message="No result found"), 404

    @blueprint.app_errorhandler(SQLAlchemyError)
    def db_error(e):
        current_app.logger.error(e)
        return jsonify(result='error', message=str(e)), 500
