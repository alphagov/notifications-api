from flask import (jsonify, request)
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound
from app.dao.services_dao import get_model_services
from app.dao.users_dao import (
    get_model_users, save_model_user, delete_model_user)
from app.schemas import (
    user_schema, users_schema, service_schema, services_schema)
from app import db


from flask import Blueprint
user = Blueprint('user', __name__)


@user.route('', methods=['POST'])
def create_user():
    user, errors = user_schema.load(request.get_json())
    req_json = request.get_json()
    # TODO password policy, what is valid password
    if not req_json.get('password'):
        errors = {'password': ['Missing data for required field.']}
        return jsonify(result="error", message=errors), 400
    if errors:
        return jsonify(result="error", message=errors), 400

    user.password = req_json.get('password')
    save_model_user(user)
    return jsonify(data=user_schema.dump(user).data), 201


@user.route('/<int:user_id>', methods=['PUT', 'DELETE'])
def update_user(user_id):
    try:
        user = get_model_users(user_id=user_id)
    except DataError:
        return jsonify(result="error", message="Invalid user id"), 400
    except NoResultFound:
        return jsonify(result="error", message="User not found"), 404
    if request.method == 'DELETE':
        status_code = 202
        delete_model_user(user)
    else:
        # TODO removed some validation checking by using load
        # which will need to be done in another way
        status_code = 200
        db.session.rollback()
        save_model_user(user, update_dict=request.get_json())
    return jsonify(data=user_schema.dump(user).data), status_code


@user.route('/<int:user_id>/verify/password', methods=['POST'])
def verify_user_password(user_id):
    try:
        user = get_model_users(user_id=user_id)
    except DataError:
        return jsonify(result="error", message="Invalid user id"), 400
    except NoResultFound:
        return jsonify(result="error", message="User not found"), 404
    text_pwd = None
    try:
        text_pwd = request.get_json()['password']
    except KeyError:
        return jsonify(
            result="error",
            message={'password': ['Required field missing data']}), 400
    if user.check_password(text_pwd):
        return jsonify(), 204
    else:
        return jsonify(result='error', message={'password': ['Incorrect password']}), 400


@user.route('/<int:user_id>', methods=['GET'])
@user.route('', methods=['GET'])
def get_user(user_id=None):
    try:
        users = get_model_users(user_id=user_id)
    except DataError:
        return jsonify(result="error", message="Invalid user id"), 400
    except NoResultFound:
        return jsonify(result="error", message="User not found"), 404
    result = users_schema.dump(users) if isinstance(users, list) else user_schema.dump(users)
    return jsonify(data=result.data)


@user.route('/<int:user_id>/service', methods=['GET'])
@user.route('/<int:user_id>/service/<int:service_id>', methods=['GET'])
def get_service_by_user_id(user_id, service_id=None):
    try:
        user = get_model_users(user_id=user_id)
    except DataError:
        return jsonify(result="error", message="Invalid user id"), 400
    except NoResultFound:
        return jsonify(result="error", message="User not found"), 404

    try:
        services = get_model_services(user_id=user.id, service_id=service_id)
    except DataError:
        return jsonify(result="error", message="Invalid service id"), 400
    except NoResultFound:
        return jsonify(result="error", message="Service not found"), 404
    services, errors = services_schema.dump(services) if isinstance(services, list) else service_schema.dump(services)
    return jsonify(data=services)
