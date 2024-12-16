from flask import request
from werkzeug.exceptions import BadRequest

from app.v2.errors.errors import BadRequestError


def get_valid_json():
    try:
        request_json = request.get_json(force=True)
    except BadRequest as e:
        raise BadRequestError(message="Invalid JSON supplied in POST data", status_code=400) from e
    return request_json or {}
