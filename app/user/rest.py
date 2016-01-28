from datetime import datetime
from flask import (jsonify, request, abort)
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound
from app.dao.services_dao import get_model_services
from app.dao.users_dao import (
    get_model_users, save_model_user, delete_model_user,
    create_user_code, get_user_code, use_user_code, increment_failed_login_count)
from app.schemas import (
    user_schema, users_schema, service_schema, services_schema,
    verify_code_schema, user_schema_load_json)
from app import db, notify_alpha_client
from flask import Blueprint


user = Blueprint('user', __name__)


@user.route('', methods=['POST'])
def create_user():
    user, errors = user_schema.load(request.get_json())
    req_json = request.get_json()
    # TODO password policy, what is valid password
    if not req_json.get('password', None):
        errors.update({'password': ['Missing data for required field.']})
        return jsonify(result="error", message=errors), 400
    if errors:
        return jsonify(result="error", message=errors), 400
    save_model_user(user, pwd=req_json.get('password'))
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
        req_json = request.get_json()
        update_dct, errors = user_schema_load_json.load(req_json)
        pwd = req_json.get('password', None)
        # TODO password validation, it is already done on the admin app
        # but would be good to have the same validation here.
        if pwd is not None and not pwd:
            errors.update({'password': ['Invalid data for field']})
        if errors:
            return jsonify(result="error", message=errors), 400
        status_code = 200
        save_model_user(user, update_dict=update_dct, pwd=pwd)
    return jsonify(data=user_schema.dump(user).data), status_code


@user.route('/<int:user_id>/verify/password', methods=['POST'])
def verify_user_password(user_id):
    try:
        user = get_model_users(user_id=user_id)
    except DataError:
        return jsonify(result="error", message="Invalid user id"), 400
    except NoResultFound:
        return jsonify(result="error", message="User not found"), 404
    txt_pwd = None
    try:
        txt_pwd = request.get_json()['password']
    except KeyError:
        return jsonify(
            result="error",
            message={'password': ['Required field missing data']}), 400
    if user.check_password(txt_pwd):
        return jsonify({}), 204
    else:
        increment_failed_login_count(user)
        return jsonify(result='error', message={'password': ['Incorrect password']}), 400


@user.route('/<int:user_id>/verify/code', methods=['POST'])
def verify_user_code(user_id):
    try:
        user = get_model_users(user_id=user_id)
    except DataError:
        return jsonify(result="error", message="Invalid user id"), 400
    except NoResultFound:
        return jsonify(result="error", message="User not found"), 404
    txt_code = None
    resp_json = request.get_json()
    txt_type = None
    errors = {}
    try:
        txt_code = resp_json['code']
    except KeyError:
        errors.update({'code': ['Required field missing data']})
    try:
        txt_type = resp_json['code_type']
    except KeyError:
        errors.update({'code_type': ['Required field missing data']})
    if errors:
        return jsonify(result="error", message=errors), 400
    code = get_user_code(user, txt_code, txt_type)
    if not code:
        return jsonify(result="error", message="Code not found"), 404
    if datetime.now() > code.expiry_datetime or code.code_used:
        return jsonify(result="error", message="Code has expired"), 400
    use_user_code(code.id)
    return jsonify({}), 204


@user.route('/<int:user_id>/code', methods=['POST'])
def send_user_code(user_id):
    try:
        user = get_model_users(user_id=user_id)
    except DataError:
        return jsonify(result="error", message="Invalid user id"), 400
    except NoResultFound:
        return jsonify(result="error", message="User not found"), 404

    request_json = request.get_json()

    verify_code, errors = verify_code_schema.load(request_json)
    if errors:
        return jsonify(result="error", message=errors), 400

    from app.dao.users_dao import create_secret_code
    secret_code = create_secret_code()
    create_user_code(user, secret_code, verify_code.code_type)
    # TODO this will need to fixed up when we stop using
    # notify_alpha_client
    if verify_code.code_type == 'sms':
        mobile = user.mobile_number if 'to' not in request_json else request_json['to']
        notify_alpha_client.send_sms(
            mobile_number=mobile,
            message=secret_code)
    elif verify_code.code_type == 'email':
        email = user.email_address if 'to' not in request_json else request_json['to']
        notify_alpha_client.send_email(
            email,
            secret_code,
            'notify@digital.cabinet-office.gov.uk',
            'Verification code')
    else:
        abort(500)
    return jsonify({}), 204


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
