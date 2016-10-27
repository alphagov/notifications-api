from flask import jsonify, current_app
from app.errors import InvalidRequest


class TooManyRequestsError(InvalidRequest):
    status_code = 429
    # code and link will be in a static file
    code = "10429"
    link = "link to docs"
    message_template = 'Exceeded send limits ({}) for today'

    def __init__(self, sending_limit):
        self.message = self.message_template.format(sending_limit)


class BadRequestError(InvalidRequest):
    status_code = 400
    code = "10400"
    link = "link to documentation"
    message = "An error occurred"

    def __init__(self, fields, message=None):
        self.fields = fields
        self.message = message if message else self.message


def register_errors(blueprint):
    @blueprint.errorhandler(InvalidRequest)
    def invalid_data(error):
        current_app.logger.error(error)
        response = jsonify(error.to_dict_v2()), error.status_code
        return response

    @blueprint.errorhandler(Exception)
    def authentication_error(error):
        # v2 error format - NOT this
        return jsonify(result='error', message=error.message), error.code
