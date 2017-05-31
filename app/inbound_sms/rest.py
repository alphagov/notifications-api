from flask import (
    Blueprint,
    jsonify,
    request
)
from notifications_utils.recipients import normalise_phone_number

from app.dao.inbound_sms_dao import dao_get_inbound_sms_for_service, dao_count_inbound_sms_for_service
from app.errors import register_errors

inbound_sms = Blueprint(
    'inbound_sms',
    __name__,
    url_prefix='/service/<service_id>/inbound-sms'
)

register_errors(inbound_sms)


@inbound_sms.route('')
def get_inbound_sms_for_service(service_id):
    limit = request.args.get('limit')
    user_number = request.args.get('user_number')

    if user_number:
        user_number = normalise_phone_number(user_number)

    results = dao_get_inbound_sms_for_service(service_id, limit, user_number)

    return jsonify(data=[row.serialize() for row in results])


@inbound_sms.route('/summary')
def get_inbound_sms_summary_for_service(service_id):
    count = dao_count_inbound_sms_for_service(service_id)
    most_recent = dao_get_inbound_sms_for_service(service_id, limit=1)

    return jsonify(
        count=count,
        most_recent=most_recent[0].created_at.isoformat() if most_recent else None
    )
