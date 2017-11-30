from flask import (
    Blueprint,
    jsonify,
    request,
)
from sqlalchemy.exc import SQLAlchemyError

from app.errors import (
    register_errors
)
from app.models import (
    ServiceInboundApi,
    ServiceCallbackApi
)
from app.schema_validation import validate
from app.service.service_callback_api_schema import (
    create_service_callback_api_schema,
    update_service_callback_api_schema
)
from app.dao.service_inbound_api_dao import (
    save_service_inbound_api,
    get_service_inbound_api,
    reset_service_inbound_api
)
from app.dao.service_callback_api_dao import (
    save_service_callback_api,
    get_service_callback_api,
    reset_service_callback_api
)

service_callback_blueprint = Blueprint('service_callback', __name__, url_prefix='/service/<uuid:service_id>')

register_errors(service_callback_blueprint)


@service_callback_blueprint.route('/inbound-api', methods=['POST'])
def create_service_inbound_api(service_id):
    data = request.get_json()
    validate(data, create_service_callback_api_schema)
    data["service_id"] = service_id
    inbound_api = ServiceInboundApi(**data)
    try:
        save_service_inbound_api(inbound_api)
    except SQLAlchemyError as e:
        return handle_sql_error(e, 'service_inbound_api')

    return jsonify(data=inbound_api.serialize()), 201


@service_callback_blueprint.route('/inbound-api/<uuid:inbound_api_id>', methods=['POST'])
def update_service_inbound_api(service_id, inbound_api_id):
    data = request.get_json()
    validate(data, update_service_callback_api_schema)

    to_update = get_service_inbound_api(inbound_api_id, service_id)

    reset_service_inbound_api(service_inbound_api=to_update,
                              updated_by_id=data["updated_by_id"],
                              url=data.get("url", None),
                              bearer_token=data.get("bearer_token", None))
    return jsonify(data=to_update.serialize()), 200


@service_callback_blueprint.route('/inbound-api/<uuid:inbound_api_id>', methods=["GET"])
def fetch_service_inbound_api(service_id, inbound_api_id):
    inbound_api = get_service_inbound_api(inbound_api_id, service_id)

    return jsonify(data=inbound_api.serialize()), 200


@service_callback_blueprint.route('/delivery-receipt-api', methods=['POST'])
def create_service_callback_api(service_id):
    data = request.get_json()
    validate(data, create_service_callback_api_schema)
    data["service_id"] = service_id
    callback_api = ServiceCallbackApi(**data)
    try:
        save_service_callback_api(callback_api)
    except SQLAlchemyError as e:
        return handle_sql_error(e, 'service_callback_api')

    return jsonify(data=callback_api.serialize()), 201


@service_callback_blueprint.route('/delivery-receipt-api/<uuid:callback_api_id>', methods=['POST'])
def update_service_callback_api(service_id, callback_api_id):
    data = request.get_json()
    validate(data, update_service_callback_api_schema)

    to_update = get_service_callback_api(callback_api_id, service_id)

    reset_service_callback_api(service_callback_api=to_update,
                               updated_by_id=data["updated_by_id"],
                               url=data.get("url", None),
                               bearer_token=data.get("bearer_token", None))
    return jsonify(data=to_update.serialize()), 200


@service_callback_blueprint.route('/delivery-receipt-api/<uuid:callback_api_id>', methods=["GET"])
def fetch_service_callback_api(service_id, callback_api_id):
    callback_api = get_service_callback_api(callback_api_id, service_id)

    return jsonify(data=callback_api.serialize()), 200


def handle_sql_error(e, table_name):
    if hasattr(e, 'orig') and hasattr(e.orig, 'pgerror') and e.orig.pgerror \
            and ('duplicate key value violates unique constraint "ix_{}_service_id"'.format(table_name)
                 in e.orig.pgerror):
        return jsonify(
            result='error',
            message={'name': ["You can only have one URL and bearer token for your service."]}
        ), 400
    elif hasattr(e, 'orig') and hasattr(e.orig, 'pgerror') and e.orig.pgerror \
            and ('insert or update on table "{0}" violates '
                 'foreign key constraint "{0}_service_id_fkey"'.format(table_name)
                 in e.orig.pgerror):
        return jsonify(result='error', message="No result found"), 404
    else:
        raise e
