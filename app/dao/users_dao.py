from random import (SystemRandom)
from datetime import (datetime, timedelta)
import uuid

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app import db
from app.dao.permissions_dao import permission_dao
from app.dao.service_user_dao import dao_get_service_users_by_user_id
from app.dao.dao_utils import transactional
from app.errors import InvalidRequest
from app.models import (EMAIL_AUTH_TYPE, User, VerifyCode)
from app.utils import escape_special_characters


def _remove_values_for_keys_if_present(dict, keys):
    for key in keys:
        dict.pop(key, None)


def create_secret_code():
    return ''.join(map(str, [SystemRandom().randrange(10) for i in range(5)]))


def save_user_attribute(usr, update_dict={}):
    db.session.query(User).filter_by(id=usr.id).update(update_dict)
    db.session.commit()


def save_model_user(usr, update_dict={}, pwd=None):
    if pwd:
        usr.password = pwd
        usr.password_changed_at = datetime.utcnow()
    if update_dict:
        _remove_values_for_keys_if_present(update_dict, ['id', 'password_changed_at'])
        db.session.query(User).filter_by(id=usr.id).update(update_dict)
    else:
        db.session.add(usr)
    db.session.commit()


def create_user_code(user, code, code_type):
    verify_code = VerifyCode(code_type=code_type,
                             expiry_datetime=datetime.utcnow() + timedelta(minutes=30),
                             user=user)
    verify_code.code = code
    db.session.add(verify_code)
    db.session.commit()
    return verify_code


def get_user_code(user, code, code_type):
    # Get the most recent codes to try and reduce the
    # time searching for the correct code.
    codes = VerifyCode.query.filter_by(
        user=user, code_type=code_type).order_by(
        VerifyCode.created_at.desc())
    return next((x for x in codes if x.check_code(code)), None)


def delete_codes_older_created_more_than_a_day_ago():
    deleted = db.session.query(VerifyCode).filter(
        VerifyCode.created_at < datetime.utcnow() - timedelta(hours=24)
    ).delete()
    db.session.commit()
    return deleted


def use_user_code(id):
    verify_code = VerifyCode.query.get(id)
    verify_code.code_used = True
    db.session.add(verify_code)
    db.session.commit()


def delete_model_user(user):
    db.session.delete(user)
    db.session.commit()


def delete_user_verify_codes(user):
    VerifyCode.query.filter_by(user=user).delete()
    db.session.commit()


def count_user_verify_codes(user):
    query = VerifyCode.query.filter(
        VerifyCode.user == user,
        VerifyCode.expiry_datetime > datetime.utcnow(),
        VerifyCode.code_used.is_(False)
    )
    return query.count()


def get_user_by_id(user_id=None):
    if user_id:
        return User.query.filter_by(id=user_id).one()
    return User.query.filter_by().all()


def get_user_by_email(email):
    return User.query.filter(func.lower(User.email_address) == func.lower(email)).one()


def get_users_by_partial_email(email):
    email = escape_special_characters(email)
    return User.query.filter(User.email_address.ilike("%{}%".format(email))).all()


def increment_failed_login_count(user):
    user.failed_login_count += 1
    db.session.add(user)
    db.session.commit()


def reset_failed_login_count(user):
    if user.failed_login_count > 0:
        user.failed_login_count = 0
        db.session.add(user)
        db.session.commit()


def update_user_password(user, password):
    # reset failed login count - they've just reset their password so should be fine
    user.password = password
    user.password_changed_at = datetime.utcnow()
    db.session.add(user)
    db.session.commit()


def get_user_and_accounts(user_id):
    return User.query.filter(
        User.id == user_id
    ).options(
        # eagerly load the user's services and organisations, and also the service's org and vice versa
        # (so we can see if the user knows about it)
        joinedload('services'),
        joinedload('organisations'),
        joinedload('organisations.services'),
        joinedload('services.organisation'),
    ).one()


@transactional
def dao_archive_user(user):
    if not user_can_be_archived(user):
        msg = "User can’t be removed from a service - check all services have another team member with manage_settings"
        raise InvalidRequest(msg, 400)

    permission_dao.remove_user_service_permissions_for_all_services(user)

    service_users = dao_get_service_users_by_user_id(user.id)
    for service_user in service_users:
        db.session.delete(service_user)

    user.organisations = []

    user.auth_type = EMAIL_AUTH_TYPE
    user.email_address = get_archived_email_address(user.email_address)
    user.mobile_number = None
    user.password = str(uuid.uuid4())
    # Changing the current_session_id signs the user out
    user.current_session_id = '00000000-0000-0000-0000-000000000000'
    user.state = 'inactive'

    db.session.add(user)


def user_can_be_archived(user):
    active_services = [x for x in user.services if x.active]

    for service in active_services:
        other_active_users = [x for x in service.users if x.state == 'active' and x != user]

        if not other_active_users:
            return False

        if not any('manage_settings' in user.get_permissions(service.id) for user in other_active_users):
            # no-one else has manage settings
            return False

    return True


def get_archived_email_address(email_address):
    date = datetime.utcnow().strftime("%Y-%m-%d")
    return '_archived_{}_{}'.format(date, email_address)
