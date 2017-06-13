from flask import (
    Blueprint,
    jsonify,
    request,
    current_app, json)
from jsonschema import ValidationError

from notifications_utils.recipients import validate_and_format_phone_number

from app.dao.inbound_sms_dao import (
    dao_get_inbound_sms_for_service,
    dao_count_inbound_sms_for_service,
    dao_get_inbound_sms_by_id
)
from app.errors import register_errors
from app.schema_validation import validate

from app.inbound_sms.inbound_sms_schemas import get_inbound_sms_for_service_schema

inbound_sms = Blueprint(
    'inbound_sms',
    __name__,
    url_prefix='/service/<uuid:service_id>/inbound-sms'
)

register_errors(inbound_sms)


@inbound_sms.route('', methods=['POST', 'GET'])
def get_inbound_sms_for_service(service_id):

    if request.method == 'GET':
        limit = request.args.get('limit')
        user_number = request.args.get('user_number')

        if user_number:
            # we use this to normalise to an international phone number
            user_number = validate_and_format_phone_number(user_number, international=True)

        results = dao_get_inbound_sms_for_service(service_id, limit, user_number)

        return jsonify(data=[row.serialize() for row in results])
    else:
        form = validate(request.get_json(), get_inbound_sms_for_service_schema)
        results = dao_get_inbound_sms_for_service(service_id, form.get('limit'), form.get('phone_number'))

        return jsonify(data=[row.serialize() for row in results])


@inbound_sms.route('/summary')
def get_inbound_sms_summary_for_service(service_id):
    count = dao_count_inbound_sms_for_service(service_id)
    most_recent = dao_get_inbound_sms_for_service(service_id, limit=1)

    return jsonify(
        count=count,
        most_recent=most_recent[0].created_at.isoformat() if most_recent else None
    )


@inbound_sms.route('/<uuid:inbound_sms_id>', methods=['GET'])
def get_inbound_by_id(service_id, inbound_sms_id):
    message = dao_get_inbound_sms_by_id(service_id, inbound_sms_id)

    return jsonify(message.serialize()), 200
