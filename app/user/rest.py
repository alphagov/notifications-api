from datetime import datetime
from flask import (jsonify, request, abort, Blueprint, current_app)
from app import encryption

from app.dao.users_dao import (
    get_model_users,
    save_model_user,
    create_user_code,
    get_user_code,
    use_user_code,
    increment_failed_login_count,
    reset_failed_login_count,
    get_user_by_email
)

from app.dao.permissions_dao import permission_dao
from app.dao.services_dao import dao_fetch_service_by_id

from app.schemas import (
    old_request_verify_code_schema,
    user_schema,
    request_verify_code_schema,
    user_schema_load_json,
    permission_schema
)

from app.celery.tasks import (send_sms_code, send_email_code)
from app.errors import register_errors

user = Blueprint('user', __name__)
register_errors(user)


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


@user.route('/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    user_to_update = get_model_users(user_id=user_id)
    if not user_to_update:
        return jsonify(result="error", message="User not found"), 404

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
    save_model_user(user_to_update, update_dict=update_dct, pwd=pwd)
    return jsonify(data=user_schema.dump(user_to_update).data), status_code


@user.route('/<int:user_id>/verify/password', methods=['POST'])
def verify_user_password(user_id):
    user_to_verify = get_model_users(user_id=user_id)

    txt_pwd = None
    try:
        txt_pwd = request.get_json()['password']
    except KeyError:
        return jsonify(
            result="error",
            message={'password': ['Required field missing data']}), 400
    if user_to_verify.check_password(txt_pwd):
        reset_failed_login_count(user_to_verify)
        return jsonify({}), 204
    else:
        increment_failed_login_count(user_to_verify)
        return jsonify(result='error', message={'password': ['Incorrect password']}), 400


@user.route('/<int:user_id>/verify/code', methods=['POST'])
def verify_user_code(user_id):
    user_to_verify = get_model_users(user_id=user_id)

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
    code = get_user_code(user_to_verify, txt_code, txt_type)
    if not code:
        return jsonify(result="error", message="Code not found"), 404
    if datetime.now() > code.expiry_datetime or code.code_used:
        return jsonify(result="error", message="Code has expired"), 400
    use_user_code(code.id)
    return jsonify({}), 204


@user.route('/<int:user_id>/sms-code', methods=['POST'])
def send_user_sms_code(user_id):
    user_to_send_to = get_model_users(user_id=user_id)

    if not user_to_send_to:
        return jsonify(result="error", message="No user found"), 404

    verify_code, errors = request_verify_code_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400

    from app.dao.users_dao import create_secret_code
    secret_code = create_secret_code()
    create_user_code(user_to_send_to, secret_code, 'sms')

    mobile = user_to_send_to.mobile_number if verify_code.get('to', None) is None else verify_code.get('to')
    verification_message = {'to': mobile, 'secret_code': secret_code}

    send_sms_code.apply_async([encryption.encrypt(verification_message)], queue='sms-code')

    return jsonify({}), 204


@user.route('/<int:user_id>/email-code', methods=['POST'])
def send_user_email_code(user_id):
    user_to_send_to = get_model_users(user_id=user_id)
    if not user_to_send_to:
        return jsonify(result="error", message="No user found"), 404

    verify_code, errors = request_verify_code_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400

    from app.dao.users_dao import create_secret_code
    secret_code = create_secret_code()
    create_user_code(user_to_send_to, secret_code, 'email')

    email = user_to_send_to.email_address if verify_code.get('to', None) is None else verify_code.get('to')
    verification_message = {'to': email, 'secret_code': secret_code}

    send_email_code.apply_async([encryption.encrypt(verification_message)], queue='email-code')

    return jsonify({}), 204


@user.route('/<int:user_id>', methods=['GET'])
@user.route('', methods=['GET'])
def get_user(user_id=None):
    users = get_model_users(user_id=user_id)
    if not users:
        return jsonify(result="error", message="not found"), 404
    result = user_schema.dump(users, many=True) if isinstance(users, list) else user_schema.dump(users)
    return jsonify(data=result.data)


@user.route('/<int:user_id>/<service_id>/permission', methods=['POST'])
def set_permissions(user_id, service_id):
    # TODO fix security hole, how do we verify that the user
    # who is making this request has permission to make the request.
    user = get_model_users(user_id=user_id)
    if not user:
        abort(404, 'User not found for id: {}'.format(user_id))
    service = dao_fetch_service_by_id(service_id=service_id)
    if not service:
        abort(404, 'Service not found for id: {}'.format(service_id))
    permissions, errors = permission_schema.load(request.get_json(), many=True)
    if errors:
        abort(400, errors)
    for p in permissions:
        p.user = user
        p.service = service
    permission_dao.set_user_permission(user, permissions)
    return jsonify({}), 204


@user.route('/email', methods=['GET'])
def get_by_email():
    email = request.args.get('email')
    if not email:
        return jsonify(result="error", message="invalid request"), 400
    user = get_user_by_email(email)
    if not user:
        return jsonify(result="error", message="not found"), 404
    result = user_schema.dump(user)

    return jsonify(data=result.data)
