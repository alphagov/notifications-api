from flask import (jsonify, request)
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound
from app.dao.services_dao import (create_model_service, get_model_services)
from app.dao.users_dao import get_model_users
from .. import service
from app.schemas import (services_schema, service_schema)


# TODO auth to be added.
@service.route('/', methods=['POST'])
def create_service():
    # TODO what exceptions get passed from schema parsing?
    service = service_schema.load(request.get_json()).data
    print(service_schema.dump(service).data)
    # Some magic here, it automatically creates the service object.
    # Cool but need to understand how this works.
    return jsonify(data=service_schema.dump(service).data), 201


# TODO auth to be added
@service.route('/<int:service_id>', methods=['PUT'])
def update_service(service_id):
    service = get_services(service_id=service_id)
    return jsonify(data=service_schema.dump(service).data)


# TODO auth to be added.
@service.route('/<int:service_id>', methods=['GET'])
@service.route('/', methods=['GET'])
def get_service(service_id=None):
    try:
        services = get_model_services(service_id=service_id)
    except DataError:
        return jsonify(result="error", message="Invalid service id"), 400
    except NoResultFound:
        return jsonify(result="error", message="Service doesn't exist"), 404
    result = services_schema.dump(services) if isinstance(services, list) else service_schema.dump(services)
    return jsonify(data=result.data)
