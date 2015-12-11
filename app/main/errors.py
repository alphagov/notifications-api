from flask import jsonify

from . import main


@main.app_errorhandler(400)
def bad_request(e):
    return jsonify(error=str(e.description)), 400


@main.app_errorhandler(401)
def unauthorized(e):
    error_message = "Unauthorized, authentication token must be provided"
    return jsonify(error=error_message), 401, [('WWW-Authenticate', 'Bearer')]


@main.app_errorhandler(403)
def forbidden(e):
    error_message = "Forbidden, invalid authentication token provided"
    return jsonify(error=error_message), 403


@main.app_errorhandler(404)
def page_not_found(e):
    return jsonify(error=e.description or "Not found"), 404


@main.app_errorhandler(429)
def limit_exceeded(e):
    return jsonify(error=str(e.description)), 429


@main.app_errorhandler(500)
def internal_server_error(e):
    # TODO: log the error
    return jsonify(error="Internal error"), 500
