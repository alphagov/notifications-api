from flask import jsonify

from app.dao.broadcast_message_dao import dao_get_all_broadcast_messages
from app.v2.govuk_alerts import v2_govuk_alerts_blueprint


@v2_govuk_alerts_blueprint.route('')
def get_broadcasts():
    all_broadcasts = dao_get_all_broadcast_messages()
    return jsonify(all_broadcasts)
