from flask import jsonify

from app.errors import InvalidRequest


class BadRequestError(Exception):
    status_code = 400

    def __init__(self, message, fields, code):
        self.code = code
        self.message = message
        self.fields = fields


def register_errors(blueprint):
    @blueprint.app_errorhandler(Exception)
    def authentication_error(error):
        # v2 error format - NOT this
        return jsonify(result='error', message=error.message), error.code

    @blueprint.app_errorhandler(InvalidRequest)
    def handle_invalid_request(error):
        # {
        #     "code",
        #     "link",
        #     "message" ,
        #     "fields":
        # }
        return "build_error_message"
