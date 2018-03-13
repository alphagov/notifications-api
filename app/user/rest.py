import json
import uuid
from datetime import datetime
from urllib.parse import urlencode

from flask import (jsonify, request, Blueprint, current_app, abort)
from sqlalchemy.exc import IntegrityError

from app.config import QueueNames
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
    count_user_verify_codes,
    get_user_and_accounts
)
from app.dao.permissions_dao import permission_dao
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.models import KEY_TYPE_NORMAL, Service, SMS_TYPE, EMAIL_TYPE
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue
)
from app.schemas import (
    email_data_request_schema,
    create_user_schema,
    permission_schema,
    user_update_schema_load_json,
    user_update_password_schema_load_json
)
from app.errors import (
    register_errors,
    InvalidRequest
)
from app.utils import url_with_token
from app.user.users_schema import (
    post_verify_code_schema,
    post_send_user_sms_code_schema,
    post_send_user_email_code_schema,
)
from app.schema_validation import validate

user_blueprint = Blueprint('user', __name__)
register_errors(user_blueprint)


@user_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the auth type/mobile number check constraint
    """
    if 'ck_users_mobile_or_email_auth' in str(exc):
        # we don't expect this to trip, so still log error
        current_app.logger.exception('Check constraint ck_users_mobile_or_email_auth triggered')
        return jsonify(result='error', message='Mobile number must be set if auth_type is set to sms_auth'), 400

    raise


@user_blueprint.route('', methods=['POST'])
def create_user():
    user_to_create, errors = create_user_schema.load(request.get_json())
    req_json = request.get_json()
    if not req_json.get('password', None):
        errors.update({'password': ['Missing data for required field.']})
        raise InvalidRequest(errors, status_code=400)
    save_model_user(user_to_create, pwd=req_json.get('password'))
    result = user_to_create.serialize()
    return jsonify(data=result), 201


@user_blueprint.route('/<uuid:user_id>', methods=['POST'])
def update_user_attribute(user_id):
    user_to_update = get_user_by_id(user_id=user_id)
    req_json = request.get_json()
    update_dct, errors = user_update_schema_load_json.load(req_json)
    if errors:
        raise InvalidRequest(errors, status_code=400)
    save_user_attribute(user_to_update, update_dict=update_dct)
    return jsonify(data=user_to_update.serialize()), 200


@user_blueprint.route('/<uuid:user_id>/activate', methods=['POST'])
def activate_user(user_id):
    user = get_user_by_id(user_id=user_id)
    if user.state == 'active':
        raise InvalidRequest('User already active', status_code=400)

    user.state = 'active'
    save_model_user(user)
    return jsonify(data=user.serialize()), 200


@user_blueprint.route('/<uuid:user_id>/reset-failed-login-count', methods=['POST'])
def user_reset_failed_login_count(user_id):
    user_to_update = get_user_by_id(user_id=user_id)
    reset_failed_login_count(user_to_update)
    return jsonify(data=user_to_update.serialize()), 200


@user_blueprint.route('/<uuid:user_id>/verify/password', methods=['POST'])
def verify_user_password(user_id):
    user_to_verify = get_user_by_id(user_id=user_id)

    try:
        txt_pwd = request.get_json()['password']
    except KeyError:
        message = 'Required field missing data'
        errors = {'password': [message]}
        raise InvalidRequest(errors, status_code=400)

    if user_to_verify.check_password(txt_pwd):
        reset_failed_login_count(user_to_verify)
        return jsonify({}), 204
    else:
        increment_failed_login_count(user_to_verify)
        message = 'Incorrect password'
        errors = {'password': [message]}
        raise InvalidRequest(errors, status_code=400)


@user_blueprint.route('/<uuid:user_id>/verify/code', methods=['POST'])
def verify_user_code(user_id):
    data = request.get_json()
    validate(data, post_verify_code_schema)

    user_to_verify = get_user_by_id(user_id=user_id)

    code = get_user_code(user_to_verify, data['code'], data['code_type'])
    if user_to_verify.failed_login_count >= current_app.config.get('MAX_VERIFY_CODE_COUNT'):
        raise InvalidRequest("Code not found", status_code=404)
    if not code:
        # only relevant from sms
        increment_failed_login_count(user_to_verify)
        raise InvalidRequest("Code not found", status_code=404)
    if datetime.utcnow() > code.expiry_datetime or code.code_used:
        # sms and email
        increment_failed_login_count(user_to_verify)
        raise InvalidRequest("Code has expired", status_code=400)

    user_to_verify.current_session_id = str(uuid.uuid4())
    user_to_verify.logged_in_at = datetime.utcnow()
    user_to_verify.failed_login_count = 0
    save_model_user(user_to_verify)

    use_user_code(code.id)
    return jsonify({}), 204


@user_blueprint.route('/<uuid:user_id>/<code_type>-code', methods=['POST'])
def send_user_2fa_code(user_id, code_type):
    user_to_send_to = get_user_by_id(user_id=user_id)

    if count_user_verify_codes(user_to_send_to) >= current_app.config.get('MAX_VERIFY_CODE_COUNT'):
        # Prevent more than `MAX_VERIFY_CODE_COUNT` active verify codes at a time
        current_app.logger.warn('Too many verify codes created for user {}'.format(user_to_send_to.id))
    else:
        data = request.get_json()
        if code_type == SMS_TYPE:
            validate(data, post_send_user_sms_code_schema)
            send_user_sms_code(user_to_send_to, data)
        elif code_type == EMAIL_TYPE:
            validate(data, post_send_user_email_code_schema)
            send_user_email_code(user_to_send_to, data)
        else:
            abort(404)

    return '{}', 204


def send_user_sms_code(user_to_send_to, data):
    recipient = data.get('to') or user_to_send_to.mobile_number

    secret_code = create_secret_code()
    personalisation = {'verify_code': secret_code}

    create_2fa_code(
        current_app.config['SMS_CODE_TEMPLATE_ID'],
        user_to_send_to,
        secret_code,
        recipient,
        personalisation
    )


def send_user_email_code(user_to_send_to, data):
    recipient = user_to_send_to.email_address

    secret_code = str(uuid.uuid4())
    personalisation = {
        'name': user_to_send_to.name,
        'url': _create_2fa_url(user_to_send_to, secret_code, data.get('next'), data.get('email_auth_link_host'))
    }

    create_2fa_code(
        current_app.config['EMAIL_2FA_TEMPLATE_ID'],
        user_to_send_to,
        secret_code,
        recipient,
        personalisation
    )


def create_2fa_code(template_id, user_to_send_to, secret_code, recipient, personalisation):
    template = dao_get_template_by_id(template_id)

    # save the code in the VerifyCode table
    create_user_code(user_to_send_to, secret_code, template.template_type)
    reply_to = None
    if template.template_type == SMS_TYPE:
        reply_to = template.service.get_default_sms_sender()
    elif template.template_type == EMAIL_TYPE:
        reply_to = template.service.get_default_reply_to_email_address()
    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=recipient,
        service=template.service,
        personalisation=personalisation,
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=reply_to
    )
    # Assume that we never want to observe the Notify service's research mode
    # setting for this notification - we still need to be able to log into the
    # admin even if we're doing user research using this service:
    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)


@user_blueprint.route('/<uuid:user_id>/change-email-verification', methods=['POST'])
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
            'feedback_url': current_app.config['ADMIN_BASE_URL'] + '/support'
        },
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=service.get_default_reply_to_email_address()
    )

    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)
    return jsonify({}), 204


@user_blueprint.route('/<uuid:user_id>/email-verification', methods=['POST'])
def send_new_user_email_verification(user_id):
    # when registering, we verify all users' email addresses using this function
    user_to_send_to = get_user_by_id(user_id=user_id)

    template = dao_get_template_by_id(current_app.config['NEW_USER_EMAIL_VERIFICATION_TEMPLATE_ID'])
    service = Service.query.get(current_app.config['NOTIFY_SERVICE_ID'])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=user_to_send_to.email_address,
        service=service,
        personalisation={
            'name': user_to_send_to.name,
            'url': _create_verification_url(user_to_send_to)
        },
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=service.get_default_reply_to_email_address()
    )

    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)

    return jsonify({}), 204


@user_blueprint.route('/<uuid:user_id>/email-already-registered', methods=['POST'])
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
            'feedback_url': current_app.config['ADMIN_BASE_URL'] + '/support'
        },
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=service.get_default_reply_to_email_address()
    )

    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)

    return jsonify({}), 204


@user_blueprint.route('/<uuid:user_id>', methods=['GET'])
@user_blueprint.route('', methods=['GET'])
def get_user(user_id=None):
    users = get_user_by_id(user_id=user_id)
    result = [x.serialize() for x in users] if isinstance(users, list) else users.serialize()
    return jsonify(data=result)


@user_blueprint.route('/<uuid:user_id>/service/<uuid:service_id>/permission', methods=['POST'])
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


@user_blueprint.route('/email', methods=['GET'])
def get_by_email():
    email = request.args.get('email')
    if not email:
        error = 'Invalid request. Email query string param required'
        raise InvalidRequest(error, status_code=400)
    fetched_user = get_user_by_email(email)
    result = fetched_user.serialize()
    return jsonify(data=result)


@user_blueprint.route('/reset-password', methods=['POST'])
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
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=service.get_default_reply_to_email_address()
    )

    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)

    return jsonify({}), 204


@user_blueprint.route('/<uuid:user_id>/update-password', methods=['POST'])
def update_password(user_id):
    user = get_user_by_id(user_id=user_id)
    req_json = request.get_json()
    pwd = req_json.get('_password')
    update_dct, errors = user_update_password_schema_load_json.load(req_json)
    if errors:
        raise InvalidRequest(errors, status_code=400)
    update_user_password(user, pwd)
    return jsonify(data=user.serialize()), 200


@user_blueprint.route('/<uuid:user_id>/organisations-and-services', methods=['GET'])
def get_organisations_and_services_for_user(user_id):
    user = get_user_and_accounts(user_id)
    data = {
        'organisations': [
            {
                'name': org.name,
                'id': org.id,
                'services': [
                    {
                        'id': service.id,
                        'name': service.name
                    }
                    for service in org.services
                    if service.active and service in user.services
                ]
            }
            for org in user.organisations if org.active
        ],
        'services_without_organisations': [
            {
                'id': service.id,
                'name': service.name
            } for service in user.services
            if (
                service.active and
                # include services that either aren't in an organisation, or are in an organisation,
                # but not one that the user can see.
                (
                    not service.organisation or
                    service.organisation not in user.organisations
                )
            )
        ]
    }
    return jsonify(data)


def _create_reset_password_url(email):
    data = json.dumps({'email': email, 'created_at': str(datetime.utcnow())})
    url = '/new-password/'
    return url_with_token(data, url, current_app.config)


def _create_verification_url(user):
    data = json.dumps({'user_id': str(user.id), 'email': user.email_address})
    url = '/verify-email/'
    return url_with_token(data, url, current_app.config)


def _create_confirmation_url(user, email_address):
    data = json.dumps({'user_id': str(user.id), 'email': email_address})
    url = '/user-profile/email/confirm/'
    return url_with_token(data, url, current_app.config)


def _create_2fa_url(user, secret_code, next_redir, email_auth_link_host):
    data = json.dumps({'user_id': str(user.id), 'secret_code': secret_code})
    url = '/email-auth/'
    ret = url_with_token(data, url, current_app.config, base_url=email_auth_link_host)
    if next_redir:
        ret += '?{}'.format(urlencode({'next': next_redir}))
    return ret
