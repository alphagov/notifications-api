from flask import Blueprint, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from app.constants import ServiceCallbackTypes
from app.dao.service_callback_api_dao import (
    delete_service_callback_api,
    get_service_callback_api,
    reset_service_callback_api,
    save_service_callback_api,
)
from app.dao.service_inbound_api_dao import (
    delete_service_inbound_api,
    get_service_inbound_api,
    reset_service_inbound_api,
    save_service_inbound_api,
)
from app.errors import InvalidRequest, register_errors
from app.models import ServiceCallbackApi, ServiceInboundApi
from app.schema_validation import validate
from app.service.service_callback_api_schema import (
    create_service_callback_api_schema,
    update_service_callback_api_schema,
)

service_callback_blueprint = Blueprint("service_callback", __name__, url_prefix="/service/<uuid:service_id>")

register_errors(service_callback_blueprint)


@service_callback_blueprint.route("/inbound-api", methods=["POST"])
@service_callback_blueprint.route("/delivery-receipt-api", methods=["POST"])
@service_callback_blueprint.route("/returned-letter-api", methods=["POST"])
def create_service_callback_api(service_id):
    data = request.get_json()
    validate(data, create_service_callback_api_schema)
    callback_type = data["callback_type"]
    data["service_id"] = service_id

    if callback_type == ServiceCallbackTypes.inbound_sms.value:
        del data["callback_type"]  # ServiceInboundApi doesn't have this attribute
        callback_api = ServiceInboundApi(**data)
        save_callback_api_method = save_service_inbound_api
        error_message = "service_inbound_api"
    else:
        callback_api = ServiceCallbackApi(**data)
        save_callback_api_method = save_service_callback_api
        error_message = "service_callback_api"

    try:
        save_callback_api_method(callback_api)
    except SQLAlchemyError as e:
        return handle_sql_error(e, error_message)
    return jsonify(data=callback_api.serialize()), 201


@service_callback_blueprint.route("/inbound-api/<uuid:callback_api_id>", methods=["POST"])
@service_callback_blueprint.route("/delivery-receipt-api/<uuid:callback_api_id>", methods=["POST"])
@service_callback_blueprint.route("/returned-letter-api/<uuid:callback_api_id>", methods=["POST"])
def update_service_callback_api(callback_api_id, service_id):
    data = request.get_json()
    validate(data, update_service_callback_api_schema)
    callback_type = data["callback_type"]

    if callback_type == ServiceCallbackTypes.inbound_sms.value:
        to_update = get_service_inbound_api(callback_api_id, service_id)
        reset_callback_api_method = reset_service_inbound_api
    else:
        to_update = get_service_callback_api(callback_api_id, service_id, callback_type)
        reset_callback_api_method = reset_service_callback_api

    reset_callback_api_method(
        to_update,
        data["updated_by_id"],
        data.get("url", None),
        data.get("bearer_token", None),
    )
    return jsonify(data=to_update.serialize()), 200


@service_callback_blueprint.route("/delivery-receipt-api/<uuid:callback_api_id>", methods=["GET"])
def fetch_delivery_receipt_callback_api(service_id, callback_api_id):
    callback_type = ServiceCallbackTypes.delivery_status.value
    return _fetch_service_callback_api(callback_api_id, service_id, callback_type)


@service_callback_blueprint.route("/returned-letter-api/<uuid:callback_api_id>", methods=["GET"])
def fetch_returned_letter_callback_api(service_id, callback_api_id):
    callback_type = ServiceCallbackTypes.returned_letter.value
    return _fetch_service_callback_api(callback_api_id, service_id, callback_type)


def _fetch_service_callback_api(callback_api_id, service_id, callback_type):
    callback_api = get_service_callback_api(callback_api_id, service_id, callback_type)
    return jsonify(data=callback_api.serialize()), 200


@service_callback_blueprint.route("/inbound-api/<uuid:callback_api_id>", methods=["GET"])
@service_callback_blueprint.route("/delivery-receipt-api/<uuid:callback_api_id>", methods=["GET"])
@service_callback_blueprint.route("/returned-letter-api/<uuid:callback_api_id>", methods=["GET"])
def fetch_service_callback_api(callback_api_id, service_id):
    callback_type = request.args.get("callback_type")
    if callback_type == ServiceCallbackTypes.inbound_sms.value:
        callback_api = get_service_inbound_api(callback_api_id, service_id)
    else:
        callback_api = get_service_callback_api(callback_api_id, service_id, callback_type)

    return jsonify(data=callback_api.serialize()), 200


@service_callback_blueprint.route("/inbound-api/<uuid:inbound_api_id>", methods=["DELETE"])
def remove_service_inbound_api(service_id, inbound_api_id):
    inbound_api = get_service_inbound_api(inbound_api_id, service_id)

    if not inbound_api:
        error = "Service inbound API not found"
        raise InvalidRequest(error, status_code=404)

    delete_service_inbound_api(inbound_api)
    return "", 204


@service_callback_blueprint.route("/delivery-receipt-api/<uuid:callback_api_id>", methods=["DELETE"])
def remove_delivery_receipt_callback_api(service_id, callback_api_id):
    callback_type = ServiceCallbackTypes.delivery_status.value
    _remove_service_callback_api(callback_api_id, service_id, callback_type)
    return "", 204


@service_callback_blueprint.route("/returned-letter-api/<uuid:callback_api_id>", methods=["DELETE"])
def remove_returned_letter_callback_api(service_id, callback_api_id):
    callback_type = ServiceCallbackTypes.returned_letter.value
    _remove_service_callback_api(callback_api_id, service_id, callback_type)
    return "", 204


def _remove_service_callback_api(callback_api_id, service_id, callback_type):
    callback_api = get_service_callback_api(callback_api_id, service_id, callback_type)
    if not callback_api:
        error = "Service delivery receipt callback API not found"
        raise InvalidRequest(error, status_code=404)
    delete_service_callback_api(callback_api)


def handle_sql_error(e, table_name):
    if (
        hasattr(e, "orig")
        and hasattr(e.orig, "pgerror")
        and e.orig.pgerror
        and (f'duplicate key value violates unique constraint "ix_{table_name}_service_id"' in e.orig.pgerror)
    ):
        return (
            jsonify(result="error", message={"name": ["You can only have one URL and bearer token for your service."]}),
            400,
        )
    elif (
        hasattr(e, "orig")
        and hasattr(e.orig, "pgerror")
        and e.orig.pgerror
        and (
            f'insert or update on table "{table_name}" violates '
            f'foreign key constraint "{table_name}_service_id_fkey"' in e.orig.pgerror
        )
    ):
        return jsonify(result="error", message="No result found"), 404
    else:
        raise e
