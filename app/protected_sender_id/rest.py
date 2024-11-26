from flask import Blueprint, jsonify, request

from app.errors import register_errors
from app.models import ProtectedSenderId
from app.protected_sender_id.protected_sender_schema import protected_sender_request
from app.schema_validation import validate

protected_sender_id_blueprint = Blueprint("protected-sender-id", __name__)

register_errors(protected_sender_id_blueprint)


@protected_sender_id_blueprint.route("/check")
def check_if_sender_id_is_protected():
    payload = request.args
    validate(payload, protected_sender_request)

    sender_id = payload.get("sender_id")
    organisation_id = payload.get("organisation_id")

    normalised_sender_id = "".join(sender_id.split()).lower()
    result = ProtectedSenderId.query.filter(ProtectedSenderId.sender_id == normalised_sender_id).scalar()

    is_protected_sender_id = result is not None and (
        organisation_id is None or str(organisation_id) == str(result.organisation_id)
    )

    return jsonify(is_protected_sender_id)
