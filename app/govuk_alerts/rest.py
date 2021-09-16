from flask import Blueprint, jsonify

from app.dao.broadcast_message_dao import dao_get_all_broadcast_messages
from app.errors import register_errors
from app.utils import get_dt_string_or_none

govuk_alerts_blueprint = Blueprint(
    "govuk-alerts",
    __name__,
    url_prefix='/govuk-alerts',
)

register_errors(govuk_alerts_blueprint)


@govuk_alerts_blueprint.route('')
def get_broadcasts():
    broadcasts = dao_get_all_broadcast_messages()
    broadcasts_dict = {"alerts": [{
        "id": broadcast.id,
        "reference": broadcast.reference,
        "channel": broadcast.channel,
        "content": broadcast.content,
        "areas": broadcast.areas,
        "status": broadcast.status,
        "starts_at": get_dt_string_or_none(broadcast.starts_at),
        "finishes_at": get_dt_string_or_none(broadcast.finishes_at),
        "approved_at": get_dt_string_or_none(broadcast.approved_at),
        "cancelled_at": get_dt_string_or_none(broadcast.cancelled_at),
    } for broadcast in broadcasts]}
    return jsonify(broadcasts_dict), 200
