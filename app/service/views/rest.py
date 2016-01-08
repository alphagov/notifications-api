from flask import jsonify
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound
from app.dao.services_dao import (create_service, get_services)
from app.dao.users_dao import (get_users)
from .. import service
from app.schemas import (services_schema, service_schema)


# TODO auth to be added.
@service.route('/', methods=['POST'])
def create_service():
    # Be lenient with args passed in
    parsed_data = service_schema(request.args)
    return jsonify(result="created"), 201


# TODO auth to be added
@service.route('/<int:service_id>', methods=['PUT'])
def update_service(service_id):
    service = get_services(service_id=service_id)
    return jsonify(data=service_schema.dump(service))


# TODO auth to be added.
@service.route('/<int:service_id>', methods=['GET'])
@service.route('/', methods=['GET'])
def get_service(service_id=None):
    try:
        services = get_services(service_id=service_id)
    except DataError:
        return jsonify(result="error", message="Invalid service id"), 400
    except NoResultFound:
        return jsonify(result="error", message="Service doesn't exist"), 404
    result = services_schema.dump(services) if isinstance(services, list) else service_schema.dump(services)
    return jsonify(data=result.data)
