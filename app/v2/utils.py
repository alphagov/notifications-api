from flask import request

from app.v2.errors import BadRequestError
from werkzeug.exceptions import BadRequest


def get_valid_json():
    try:
        request_json = request.get_json(force=True)
    except BadRequest:
        raise BadRequestError(message="Invalid JSON supplied in POST data",
                              status_code=400)
    return request_json or {}
