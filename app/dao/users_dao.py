import random
from datetime import (datetime, timedelta)
from sqlalchemy import func
from app import db
from app.models import (User, VerifyCode)


def _remove_values_for_keys_if_present(dict, keys):
    for key in keys:
        dict.pop(key, None)


def create_secret_code():
    return ''.join(map(str, random.sample(range(9), 5)))


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
    retval = None
    for x in codes:
        if x.check_code(code):
            retval = x
            break
    return retval


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
