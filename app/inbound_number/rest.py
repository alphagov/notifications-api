from flask import Blueprint, jsonify

from app.dao.inbound_numbers_dao import (
    dao_get_available_inbound_numbers,
    dao_get_inbound_number_for_service,
    dao_get_inbound_numbers,
    dao_set_inbound_number_active_flag,
)
from app.errors import register_errors

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


@inbound_number_blueprint.route('/service/<uuid:service_id>/off', methods=['POST'])
def post_set_inbound_number_off(service_id):
    dao_set_inbound_number_active_flag(service_id, active=False)
    return jsonify(), 204


@inbound_number_blueprint.route('/available', methods=['GET'])
def get_available_inbound_numbers():
    inbound_numbers = [i.serialize() for i in dao_get_available_inbound_numbers()]

    return jsonify(data=inbound_numbers if inbound_numbers else [])
