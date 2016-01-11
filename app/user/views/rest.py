from flask import (jsonify, request)
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound
from app.dao.services_dao import get_model_services
from app.dao.users_dao import (get_model_users, create_model_user)
from app.schemas import (
    user_schema, users_schema, service_schema, services_schema)
from .. import user


# TODO auth to be added
@user.route('/', methods=['POST'])
def create_user():
    user = user_schema.load(request.get_json()).data
    create_model_user(user)
    return jsonify(data=user_schema.dump(user).data), 201


# TODO auth to be added
@user.route('/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    user = get_model_users(user_id=user_id)
    return jsonify(data=user_schema.dump(user).data)


# TODO auth to be added.
@user.route('/<int:user_id>', methods=['GET'])
@user.route('/', methods=['GET'])
def get_user(user_id=None):
    try:
        users = get_model_users(user_id=user_id)
    except DataError:
        return jsonify(result="error", message="Invalid user id"), 400
    except NoResultFound:
        return jsonify(result="error", message="User doesn't exist"), 404
    result = users_schema.dump(users) if isinstance(users, list) else user_schema.dump(users)
    return jsonify(data=result.data)


# TODO auth to be added
@user.route('/<int:user_id>/service', methods=['GET'])
@user.route('/<int:user_id>/service/<int:service_id>', methods=['GET'])
def get_service_by_user_id(user_id, service_id=None):
    try:
        user = get_model_users(user_id=user_id)
    except DataError:
        return jsonify(result="error", message="Invalid user id"), 400
    except NoResultFound:
        return jsonify(result="error", message="User doesn't exist"), 400

    try:
        services = get_model_services(user_id=user.id, service_id=service_id)
    except DataError:
        return jsonify(result="error", message="Invalid service id"), 400
    except NoResultFound:
        return jsonify(result="error", message="Service doesn't exist"), 404
    result = services_schema.dump(services) if isinstance(services, list) else service_schema.dump(services)
    return jsonify(data=result.data)
