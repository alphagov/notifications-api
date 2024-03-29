from flask import Blueprint, jsonify, request

from app.dao.inbound_numbers_dao import (
    dao_allocate_number_for_service,
    dao_get_available_inbound_numbers,
    dao_get_inbound_number_for_service,
    dao_get_inbound_numbers,
    dao_set_inbound_number_active_flag,
)
from app.dao.service_sms_sender_dao import (
    dao_add_sms_sender_for_service,
    dao_get_sms_senders_by_service_id,
    update_existing_sms_sender_with_inbound_number,
)
from app.errors import register_errors
from app.inbound_number.inbound_number_schema import (
    add_inbound_number_to_service_request,
)
from app.schema_validation import validate

inbound_number_blueprint = Blueprint("inbound_number", __name__, url_prefix="/inbound-number")
register_errors(inbound_number_blueprint)


@inbound_number_blueprint.route("", methods=["GET"])
def get_inbound_numbers():
    inbound_numbers = [i.serialize() for i in dao_get_inbound_numbers()]

    return jsonify(data=inbound_numbers if inbound_numbers else [])


@inbound_number_blueprint.route("/service/<uuid:service_id>", methods=["GET"])
def get_inbound_number_for_service(service_id):
    inbound_number = dao_get_inbound_number_for_service(service_id)

    return jsonify(data=inbound_number.serialize() if inbound_number else {})


@inbound_number_blueprint.route("/service/<uuid:service_id>/off", methods=["POST"])
def post_set_inbound_number_off(service_id):
    dao_set_inbound_number_active_flag(service_id, active=False)
    return jsonify(), 204


@inbound_number_blueprint.route("/available", methods=["GET"])
def get_available_inbound_numbers():
    inbound_numbers = [i.serialize() for i in dao_get_available_inbound_numbers()]

    return jsonify(data=inbound_numbers if inbound_numbers else [])


@inbound_number_blueprint.route("/service/<uuid:service_id>", methods=["POST"])
def add_inbound_number_to_service(service_id):
    """
    Route to add an inbound number to a service. If inbound_number_id is provided we
    add that specific number, otherwise we add a random available number.
    """
    form = validate(request.get_json(), add_inbound_number_to_service_request)

    if form.get("inbound_number_id"):
        inbound_number_id = form["inbound_number_id"]
    else:
        try:
            available_number = dao_get_available_inbound_numbers()[0]
            inbound_number_id = available_number.id
        except IndexError as e:
            raise Exception("There are no available inbound numbers") from e

    new_inbound_number = dao_allocate_number_for_service(service_id=service_id, inbound_number_id=inbound_number_id)

    existing_sms_sender = dao_get_sms_senders_by_service_id(service_id)
    if len(existing_sms_sender) == 1:
        new_sms_sender = update_existing_sms_sender_with_inbound_number(
            service_sms_sender=existing_sms_sender[0],
            sms_sender=new_inbound_number.number,
            inbound_number_id=new_inbound_number.id,
        )
    else:
        new_sms_sender = dao_add_sms_sender_for_service(
            service_id=service_id,
            sms_sender=new_inbound_number.number,
            is_default=True,
            inbound_number_id=new_inbound_number.id,
        )

    return jsonify(new_sms_sender.serialize()), 201
