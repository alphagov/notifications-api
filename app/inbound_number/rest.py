from flask import Blueprint, jsonify

from app.dao.inbound_numbers_dao import (
    dao_get_inbound_numbers,
    dao_get_inbound_number_for_service,
    dao_get_available_inbound_numbers,
    dao_set_inbound_number_to_service,
    dao_set_inbound_number_active_flag
)
from app.errors import InvalidRequest, register_errors

inbound_number_blueprint = Blueprint('inbound_number', __name__, url_prefix='/inbound-number')
register_errors(inbound_number_blueprint)


@inbound_number_blueprint.route('', methods=['GET'])
def get_inbound_numbers():
    inbound_numbers = [i.serialize() for i in dao_get_inbound_numbers()]

    return jsonify(data=inbound_numbers if inbound_numbers else [])


@inbound_number_blueprint.route('/service/<uuid:service_id>', methods=['GET'])
def get_inbound_number_for_service(service_id):
    inbound_number = dao_get_inbound_number_for_service(service_id)

    return jsonify(data=inbound_number.serialize() if inbound_number else {})


@inbound_number_blueprint.route('/service/<uuid:service_id>', methods=['POST'])
def post_allocate_inbound_number(service_id):
    inbound_number = dao_get_inbound_number_for_service(service_id)

    if inbound_number:
        if not inbound_number.active:
            dao_set_inbound_number_active_flag(service_id, active=True)
            return '', 204
        else:
            return '', 200

    available_numbers = dao_get_available_inbound_numbers()

    if len(available_numbers) > 0:
        dao_set_inbound_number_to_service(service_id, available_numbers[0])
        return '', 204
    else:
        raise InvalidRequest('No available inbound numbers', status_code=400)


@inbound_number_blueprint.route('/service/<uuid:service_id>/off', methods=['POST'])
def post_set_inbound_number_off(service_id):
    dao_set_inbound_number_active_flag(service_id, active=False)
    return '', 204
