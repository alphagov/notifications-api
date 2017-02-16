import json
from datetime import datetime
from flask import (jsonify, request, Blueprint, current_app)
from app.dao.users_dao import (
    get_user_by_id,
    save_model_user,
    create_user_code,
    get_user_code,
    use_user_code,
    increment_failed_login_count,
    reset_failed_login_count,
    get_user_by_email,
    create_secret_code,
    save_user_attribute,
    update_user_password,
    count_user_verify_codes
)
from app.dao.permissions_dao import permission_dao
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.models import SMS_TYPE, KEY_TYPE_NORMAL, EMAIL_TYPE, Service
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue
)
from app.schemas import (
    email_data_request_schema,
    user_schema,
    request_verify_code_schema,
    permission_schema,
    user_schema_load_json,
    user_update_schema_load_json,
    user_update_password_schema_load_json
)

from app.errors import (
    register_errors,
    InvalidRequest
)
from app.utils import url_with_token

user = Blueprint('user', __name__)
register_errors(user)


@user.route('', methods=['POST'])
def create_user():
    user_to_create, errors = user_schema.load(request.get_json())
    req_json = request.get_json()
    if not req_json.get('password', None):
        errors.update({'password': ['Missing data for required field.']})
        raise InvalidRequest(errors, status_code=400)
    save_model_user(user_to_create, pwd=req_json.get('password'))
    return jsonify(data=user_schema.dump(user_to_create).data), 201


@user.route('/<uuid:user_id>', methods=['PUT'])
def update_user(user_id):
    user_to_update = get_user_by_id(user_id=user_id)
    req_json = request.get_json()
    update_dct, errors = user_schema_load_json.load(req_json)
    pwd = req_json.get('password', None)
    # TODO password validation, it is already done on the admin app
    # but would be good to have the same validation here.
    if pwd is not None and not pwd:
        errors.update({'password': ['Invalid data for field']})
        raise InvalidRequest(errors, status_code=400)
    save_model_user(user_to_update, update_dict=update_dct, pwd=pwd)
    return jsonify(data=user_schema.dump(user_to_update).data), 200


@user.route('/<uuid:user_id>', methods=['POST'])
def update_user_attribute(user_id):
    user_to_update = get_user_by_id(user_id=user_id)
    req_json = request.get_json()
    update_dct, errors = user_update_schema_load_json.load(req_json)
    if errors:
        raise InvalidRequest(errors, status_code=400)
    save_user_attribute(user_to_update, update_dict=update_dct)
    return jsonify(data=user_schema.dump(user_to_update).data), 200


@user.route('/<uuid:user_id>/verify/password', methods=['POST'])
def verify_user_password(user_id):
    user_to_verify = get_user_by_id(user_id=user_id)

    try:
        txt_pwd = request.get_json()['password']
    except KeyError:
        message = 'Required field missing data'
        errors = {'password': [message]}
        raise InvalidRequest(errors, status_code=400)

    if user_to_verify.check_password(txt_pwd):
        user_to_verify.logged_in_at = datetime.utcnow()
        save_model_user(user_to_verify)
        reset_failed_login_count(user_to_verify)
        return jsonify({}), 204
    else:
        increment_failed_login_count(user_to_verify)
        message = 'Incorrect password'
        errors = {'password': [message]}
        raise InvalidRequest(errors, status_code=400)


@user.route('/<uuid:user_id>/verify/code', methods=['POST'])
def verify_user_code(user_id):
    user_to_verify = get_user_by_id(user_id=user_id)

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
        raise InvalidRequest(errors, status_code=400)

    code = get_user_code(user_to_verify, txt_code, txt_type)
    if not code:
        increment_failed_login_count(user_to_verify)
        raise InvalidRequest("Code not found", status_code=404)
    if datetime.utcnow() > code.expiry_datetime or code.code_used:
        increment_failed_login_count(user_to_verify)
        raise InvalidRequest("Code has expired", status_code=400)
    use_user_code(code.id)
    return jsonify({}), 204


@user.route('/<uuid:user_id>/sms-code', methods=['POST'])
def send_user_sms_code(user_id):
    user_to_send_to = get_user_by_id(user_id=user_id)
    verify_code, errors = request_verify_code_schema.load(request.get_json())

    if count_user_verify_codes(user_to_send_to) >= current_app.config.get('MAX_VERIFY_CODE_COUNT'):
        # Prevent more than `MAX_VERIFY_CODE_COUNT` active verify codes at a time
        current_app.logger.warn('Max verify code has exceeded for user {}'.format(user_to_send_to.id))
        return jsonify({}), 204

    secret_code = create_secret_code()
    create_user_code(user_to_send_to, secret_code, SMS_TYPE)

    mobile = user_to_send_to.mobile_number if verify_code.get('to', None) is None else verify_code.get('to')
    sms_code_template_id = current_app.config['SMS_CODE_TEMPLATE_ID']
    sms_code_template = dao_get_template_by_id(sms_code_template_id)
    service = Service.query.get(current_app.config['NOTIFY_SERVICE_ID'])

    saved_notification = persist_notification(
        template_id=sms_code_template_id,
        template_version=sms_code_template.version,
        recipient=mobile,
        service=service,
        personalisation={'verify_code': secret_code},
        notification_type=SMS_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL
    )
    # Assume that we never want to observe the Notify service's research mode
    # setting for this notification - we still need to be able to log into the
    # admin even if we're doing user research using this service:
    send_notification_to_queue(saved_notification, False, queue='notify')

    return jsonify({}), 204


@user.route('/<uuid:user_id>/change-email-verification', methods=['POST'])
def send_user_confirm_new_email(user_id):
    user_to_send_to = get_user_by_id(user_id=user_id)
    email, errors = email_data_request_schema.load(request.get_json())
    if errors:
        raise InvalidRequest(message=errors, status_code=400)

    template = dao_get_template_by_id(current_app.config['CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID'])
    service = Service.query.get(current_app.config['NOTIFY_SERVICE_ID'])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=email['email'],
        service=service,
        personalisation={
            'name': user_to_send_to.name,
            'url': _create_confirmation_url(user=user_to_send_to, email_address=email['email']),
            'feedback_url': current_app.config['ADMIN_BASE_URL'] + '/feedback'
        },
        notification_type=EMAIL_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL
    )

    send_notification_to_queue(saved_notification, False, queue='notify')
    return jsonify({}), 204


@user.route('/<uuid:user_id>/email-verification', methods=['POST'])
def send_user_email_verification(user_id):
    user_to_send_to = get_user_by_id(user_id=user_id)
    secret_code = create_secret_code()
    create_user_code(user_to_send_to, secret_code, 'email')

    template = dao_get_template_by_id(current_app.config['EMAIL_VERIFY_CODE_TEMPLATE_ID'])
    service = Service.query.get(current_app.config['NOTIFY_SERVICE_ID'])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=user_to_send_to.email_address,
        service=service,
        personalisation={
            'name': user_to_send_to.name,
            'url': _create_verification_url(user_to_send_to, secret_code)
        },
        notification_type=EMAIL_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL
    )

    send_notification_to_queue(saved_notification, False, queue="notify")

    return jsonify({}), 204


@user.route('/<uuid:user_id>/email-already-registered', methods=['POST'])
def send_already_registered_email(user_id):
    to, errors = email_data_request_schema.load(request.get_json())
    template = dao_get_template_by_id(current_app.config['ALREADY_REGISTERED_EMAIL_TEMPLATE_ID'])
    service = Service.query.get(current_app.config['NOTIFY_SERVICE_ID'])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=to['email'],
        service=service,
        personalisation={
            'signin_url': current_app.config['ADMIN_BASE_URL'] + '/sign-in',
            'forgot_password_url': current_app.config['ADMIN_BASE_URL'] + '/forgot-password',
            'feedback_url': current_app.config['ADMIN_BASE_URL'] + '/feedback'
        },
        notification_type=EMAIL_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL
    )

    send_notification_to_queue(saved_notification, False, queue="notify")

    return jsonify({}), 204


@user.route('/<uuid:user_id>', methods=['GET'])
@user.route('', methods=['GET'])
def get_user(user_id=None):
    users = get_user_by_id(user_id=user_id)
    result = user_schema.dump(users, many=True) if isinstance(users, list) else user_schema.dump(users)
    return jsonify(data=result.data)


@user.route('/<uuid:user_id>/service/<uuid:service_id>/permission', methods=['POST'])
def set_permissions(user_id, service_id):
    # TODO fix security hole, how do we verify that the user
    # who is making this request has permission to make the request.
    user = get_user_by_id(user_id=user_id)
    service = dao_fetch_service_by_id(service_id=service_id)
    permissions, errors = permission_schema.load(request.get_json(), many=True)

    for p in permissions:
        p.user = user
        p.service = service
    permission_dao.set_user_service_permission(user, service, permissions, _commit=True, replace=True)
    return jsonify({}), 204


@user.route('/email', methods=['GET'])
def get_by_email():
    email = request.args.get('email')
    if not email:
        error = 'Invalid request. Email query string param required'
        raise InvalidRequest(error, status_code=400)
    fetched_user = get_user_by_email(email)
    result = user_schema.dump(fetched_user)

    return jsonify(data=result.data)


@user.route('/reset-password', methods=['POST'])
def send_user_reset_password():
    email, errors = email_data_request_schema.load(request.get_json())

    user_to_send_to = get_user_by_email(email['email'])

    template = dao_get_template_by_id(current_app.config['PASSWORD_RESET_TEMPLATE_ID'])
    service = Service.query.get(current_app.config['NOTIFY_SERVICE_ID'])
    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=email['email'],
        service=service,
        personalisation={
            'user_name': user_to_send_to.name,
            'url': _create_reset_password_url(user_to_send_to.email_address)
        },
        notification_type=EMAIL_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL
    )

    send_notification_to_queue(saved_notification, False, queue="notify")

    return jsonify({}), 204


@user.route('/<uuid:user_id>/update-password', methods=['POST'])
def update_password(user_id):
    user = get_user_by_id(user_id=user_id)
    req_json = request.get_json()
    pwd = req_json.get('_password')
    update_dct, errors = user_update_password_schema_load_json.load(req_json)
    if errors:
        raise InvalidRequest(errors, status_code=400)

    update_user_password(user, pwd)
    return jsonify(data=user_schema.dump(user).data), 200


def _create_reset_password_url(email):
    data = json.dumps({'email': email, 'created_at': str(datetime.utcnow())})
    url = '/new-password/'
    return url_with_token(data, url, current_app.config)


def _create_verification_url(user, secret_code):
    data = json.dumps({'user_id': str(user.id), 'email': user.email_address, 'secret_code': secret_code})
    url = '/verify-email/'
    return url_with_token(data, url, current_app.config)


def _create_confirmation_url(user, email_address):
    data = json.dumps({'user_id': str(user.id), 'email': email_address})
    url = '/user-profile/email/confirm/'
    return url_with_token(data, url, current_app.config)
