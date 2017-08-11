from flask import Blueprint, jsonify, request

from app.dao.inbound_numbers_dao import (
    dao_get_inbound_numbers,
    dao_get_inbound_number,
    dao_get_inbound_number_for_service,
    dao_get_available_inbound_numbers,
    dao_set_inbound_number_to_service,
    dao_set_inbound_number_active_flag
)
from app.errors import InvalidRequest, register_errors
from app.models import InboundNumber
from app.schema_validation import validate

inbound_number_blueprint = Blueprint('inbound_number', __name__)
register_errors(inbound_number_blueprint)


@inbound_number_blueprint.route('', methods=['GET'])
def get_inbound_numbers():
    inbound_numbers = [i.serialize() for i in dao_get_inbound_numbers()]

    return jsonify(data=inbound_numbers if inbound_numbers else None)


@inbound_number_blueprint.route('/available', methods=['GET'])
def get_next_available_inbound_numbers():
    inbound_numbers = [i.serialize() for i in dao_get_available_inbound_numbers()]

    return jsonify(data=inbound_numbers[0] if len(inbound_numbers) else [])


@inbound_number_blueprint.route('/service/<uuid:service_id>', methods=['GET'])
def get_inbound_number_for_service(service_id):
    inbound_number = dao_get_inbound_number_for_service(service_id)

    return jsonify(data=inbound_number.serialize() if inbound_number else None)


@inbound_number_blueprint.route('/<uuid:inbound_number_id>/service/<uuid:service_id>', methods=['POST'])
def post_set_inbound_number_for_service(inbound_number_id, service_id):
    inbound_number = dao_get_inbound_number_for_service(service_id)
    if inbound_number:
        raise InvalidRequest('Service already has an inbound number', status_code=400)

    inbound_number = dao_get_inbound_number(inbound_number_id)
    if inbound_number.service_id:
        raise InvalidRequest('Inbound number already assigned', status_code=400)

    dao_set_inbound_number_to_service(service_id, inbound_number)

    return '', 204


@inbound_number_blueprint.route('/<uuid:inbound_number_id>/on', methods=['POST'])
def post_set_inbound_number_on(inbound_number_id):
    dao_set_inbound_number_active_flag(inbound_number_id, active=True)
    return '', 204


@inbound_number_blueprint.route('/<uuid:inbound_number_id>/off', methods=['POST'])
def post_set_inbound_number_off(inbound_number_id):
    dao_set_inbound_number_active_flag(inbound_number_id, active=False)
    return '', 204
