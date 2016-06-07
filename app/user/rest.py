import json
import uuid
from datetime import datetime
from flask import (jsonify, request, abort, Blueprint, current_app)
from app import encryption, DATETIME_FORMAT
from app.dao.users_dao import (
    get_model_users,
    save_model_user,
    create_user_code,
    get_user_code,
    use_user_code,
    increment_failed_login_count,
    reset_failed_login_count,
    get_user_by_email,
    create_secret_code
)
from app.dao.permissions_dao import permission_dao
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.schemas import (
    email_data_request_schema,
    user_schema,
    request_verify_code_schema,
    user_schema_load_json,
    permission_schema
)

from app.celery.tasks import (
    send_sms,
    email_reset_password,
    email_registration_verification
)

from app.errors import register_errors

user = Blueprint('user', __name__)
register_errors(user)


@user.route('', methods=['POST'])
def create_user():
    user_to_create, errors = user_schema.load(request.get_json())
    req_json = request.get_json()
    # TODO password policy, what is valid password
    if not req_json.get('password', None):
        errors.update({'password': ['Missing data for required field.']})
        return jsonify(result="error", message=errors), 400
    if errors:
        return jsonify(result="error", message=errors), 400
    save_model_user(user_to_create, pwd=req_json.get('password'))
    return jsonify(data=user_schema.dump(user_to_create).data), 201


@user.route('/<uuid:user_id>', methods=['PUT'])
def update_user(user_id):
    user_to_update = get_model_users(user_id=user_id)
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


@user.route('/<uuid:user_id>/verify/password', methods=['POST'])
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
        user_to_verify.logged_in_at = datetime.utcnow()
        save_model_user(user_to_verify)
        reset_failed_login_count(user_to_verify)
        return jsonify({}), 204
    else:
        increment_failed_login_count(user_to_verify)
        return jsonify(result='error', message={'password': ['Incorrect password']}), 400


@user.route('/<uuid:user_id>/verify/code', methods=['POST'])
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
    if datetime.utcnow() > code.expiry_datetime or code.code_used:
        return jsonify(result="error", message="Code has expired"), 400
    use_user_code(code.id)
    return jsonify({}), 204


@user.route('/<uuid:user_id>/sms-code', methods=['POST'])
def send_user_sms_code(user_id):
    user_to_send_to = get_model_users(user_id=user_id)
    verify_code, errors = request_verify_code_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400

    secret_code = create_secret_code()
    create_user_code(user_to_send_to, secret_code, 'sms')

    mobile = user_to_send_to.mobile_number if verify_code.get('to', None) is None else verify_code.get('to')
    sms_code_template_id = current_app.config['SMS_CODE_TEMPLATE_ID']
    sms_code_template = dao_get_template_by_id(sms_code_template_id)
    verification_message = encryption.encrypt({
        'template': sms_code_template_id,
        'template_version': sms_code_template.version,
        'to': mobile,
        'personalisation': {
            'verify_code': secret_code
        }

    })
    send_sms.apply_async([current_app.config['NOTIFY_SERVICE_ID'],
                          str(uuid.uuid4()),
                          verification_message,
                          datetime.utcnow().strftime(DATETIME_FORMAT)
                          ], queue='sms-code')

    return jsonify({}), 204


@user.route('/<uuid:user_id>/email-verification', methods=['POST'])
def send_user_email_verification(user_id):
    user_to_send_to = get_model_users(user_id=user_id)
    verify_code, errors = request_verify_code_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400

    secret_code = create_secret_code()
    create_user_code(user_to_send_to, secret_code, 'email')

    email = user_to_send_to.email_address
    verification_message = {'to': email,
                            'name': user_to_send_to.name,
                            'url': _create_verification_url(user_to_send_to, secret_code)}

    email_registration_verification.apply_async([encryption.encrypt(verification_message)],
                                                queue='email-registration-verification')

    return jsonify({}), 204


@user.route('/<uuid:user_id>', methods=['GET'])
@user.route('', methods=['GET'])
def get_user(user_id=None):
    users = get_model_users(user_id=user_id)
    result = user_schema.dump(users, many=True) if isinstance(users, list) else user_schema.dump(users)
    return jsonify(data=result.data)


@user.route('/<uuid:user_id>/service/<uuid:service_id>/permission', methods=['POST'])
def set_permissions(user_id, service_id):
    # TODO fix security hole, how do we verify that the user
    # who is making this request has permission to make the request.
    user = get_model_users(user_id=user_id)
    service = dao_fetch_service_by_id(service_id=service_id)
    permissions, errors = permission_schema.load(request.get_json(), many=True)
    if errors:
        abort(400, errors)
    for p in permissions:
        p.user = user
        p.service = service
    permission_dao.set_user_service_permission(user, service, permissions, _commit=True, replace=True)
    return jsonify({}), 204


@user.route('/email', methods=['GET'])
def get_by_email():
    email = request.args.get('email')
    if not email:
        return jsonify(result="error", message="invalid request"), 400
    fetched_user = get_user_by_email(email)
    result = user_schema.dump(fetched_user)

    return jsonify(data=result.data)


@user.route('/reset-password', methods=['POST'])
def send_user_reset_password():
    email, errors = email_data_request_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400

    user_to_send_to = get_user_by_email(email['email'])

    reset_password_message = {'to': user_to_send_to.email_address,
                              'name': user_to_send_to.name,
                              'reset_password_url': _create_reset_password_url(user_to_send_to.email_address)}

    email_reset_password.apply_async([encryption.encrypt(reset_password_message)], queue='email-reset-password')

    return jsonify({}), 204


def _create_reset_password_url(email):
    from notifications_utils.url_safe_token import generate_token
    data = json.dumps({'email': email, 'created_at': str(datetime.utcnow())})
    token = generate_token(data, current_app.config['SECRET_KEY'], current_app.config['DANGEROUS_SALT'])

    return current_app.config['ADMIN_BASE_URL'] + '/new-password/' + token


def _create_verification_url(user, secret_code):
    from notifications_utils.url_safe_token import generate_token
    data = json.dumps({'user_id': str(user.id), 'email': user.email_address, 'secret_code': secret_code})
    token = generate_token(data, current_app.config['SECRET_KEY'], current_app.config['DANGEROUS_SALT'])

    return current_app.config['ADMIN_BASE_URL'] + '/verify-email/' + token
