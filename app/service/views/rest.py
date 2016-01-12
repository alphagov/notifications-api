from flask import (jsonify, request)
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound
from app.dao.services_dao import (save_model_service, get_model_services)
from app.dao.users_dao import get_model_users
from app.dao import DAOException
from .. import service
from app import db
from app.schemas import (services_schema, service_schema)


# TODO auth to be added.
@service.route('/', methods=['POST'])
def create_service():
    # TODO what exceptions get passed from schema parsing?
    service, errors = service_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400
    # I believe service is already added to the session but just needs a
    # db.session.commit
    try:
        save_model_service(service)
    except DAOException as e:
        return jsonify(result="error", message=str(e)), 400
    return jsonify(data=service_schema.dump(service).data), 201


# TODO auth to be added
@service.route('/<int:service_id>', methods=['PUT'])
def update_service(service_id):
    try:
        service = get_model_services(service_id=service_id)
    except DataError:
        return jsonify(result="error", message="Invalid service id"), 400
    except NoResultFound:
        return jsonify(result="error", message="Service not found"), 404
    # TODO there has got to be a better way to do the next three lines
    upd_serv, errors = service_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400
    update_dict, errors = service_schema.dump(upd_serv)
    # TODO FIX ME
    # Remove update_service model which is added to db.session
    db.session.rollback()
    try:
        save_model_service(service, update_dict=update_dict)
    except DAOException as e:
        return jsonify(result="error", message=str(e)), 400
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
        return jsonify(result="error", message="Service not found"), 404
    data, errors = services_schema.dump(services) if isinstance(services, list) else service_schema.dump(services)
    return jsonify(data=data)
