from flask import Blueprint, jsonify, request

from app.errors import InvalidRequest, register_errors
from app.models import ProtectedSenderId
from app.protected_sender_id.protected_sender_schema import protected_sender_request
from app.schema_validation import validate

protected_sender_id_blueprint = Blueprint("protected-sender-id", __name__)

register_errors(protected_sender_id_blueprint)


@protected_sender_id_blueprint.route("/check")
def check_if_sender_id_is_protected():
    if request.args:
        validate(request.args, protected_sender_request)

    sender_id = request.args.get("sender_id", "")
    if sender_id == "":
        raise InvalidRequest(message="sender_id must be passed in", status_code=400)
    normalised_sender_id = "".join(sender_id.split()).lower()
    result = ProtectedSenderId.query.filter(ProtectedSenderId.sender_id == normalised_sender_id).scalar()
    if result:
        is_protected_sender_id = True
    else:
        is_protected_sender_id = False
    return jsonify(is_protected_sender_id)
