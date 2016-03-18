from datetime import datetime, timedelta
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound

from app import db
import pytest

from app.dao.users_dao import (
    save_model_user,
    get_model_users,
    delete_model_user,
    increment_failed_login_count,
    reset_failed_login_count,
    get_user_by_email,
    delete_codes_older_created_more_than_a_day_ago
)

from tests.app.conftest import sample_user as create_sample_user
from app.models import User, VerifyCode


def test_create_user(notify_api, notify_db, notify_db_session):
    email = 'notify@digital.cabinet-office.gov.uk'
    data = {
        'name': 'Test User',
        'email_address': email,
        'password': 'password',
        'mobile_number': '+447700900986'
    }
    user = User(**data)
    save_model_user(user)
    assert User.query.count() == 1
    assert User.query.first().email_address == email
    assert User.query.first().id == user.id
    assert not user.platform_admin


def test_get_all_users(notify_api, notify_db, notify_db_session, sample_user):
    assert User.query.count() == 1
    assert len(get_model_users()) == 1
    email = "another.notify@digital.cabinet-office.gov.uk"
    another_user = create_sample_user(notify_db,
                                      notify_db_session,
                                      email=email)
    assert User.query.count() == 2
    assert len(get_model_users()) == 2


def test_get_user(notify_api, notify_db, notify_db_session):
    email = "another.notify@digital.cabinet-office.gov.uk"
    another_user = create_sample_user(notify_db,
                                      notify_db_session,
                                      email=email)
    assert get_model_users(user_id=another_user.id).email_address == email


def test_get_user_not_exists(notify_api, notify_db, notify_db_session):
    try:
        get_model_users(user_id="12345")
        pytest.fail("NoResultFound exception not thrown.")
    except NoResultFound as e:
        pass


def test_get_user_invalid_id(notify_api, notify_db, notify_db_session):
    try:
        get_model_users(user_id="blah")
        pytest.fail("DataError exception not thrown.")
    except DataError:
        pass


def test_delete_users(notify_api, notify_db, notify_db_session, sample_user):
    assert User.query.count() == 1
    delete_model_user(sample_user)
    assert User.query.count() == 0


def test_increment_failed_login_should_increment_failed_logins(notify_api, notify_db, notify_db_session, sample_user):
    assert User.query.count() == 1
    assert sample_user.failed_login_count == 0
    increment_failed_login_count(sample_user)
    assert sample_user.failed_login_count == 1


def test_reset_failed_login_should_set_failed_logins_to_0(notify_api, notify_db, notify_db_session, sample_user):
    assert User.query.count() == 1
    increment_failed_login_count(sample_user)
    assert sample_user.failed_login_count == 1
    reset_failed_login_count(sample_user)
    assert sample_user.failed_login_count == 0


def test_get_user_by_email(sample_user):
    email = sample_user.email_address
    user_from_db = get_user_by_email(email)
    assert sample_user == user_from_db


def test_should_delete_all_verification_codes_more_than_one_day_old(sample_user):
    make_verify_code(sample_user, age=timedelta(hours=24), code="54321")
    make_verify_code(sample_user, age=timedelta(hours=24), code="54321")
    assert len(VerifyCode.query.all()) == 2
    delete_codes_older_created_more_than_a_day_ago()
    assert len(VerifyCode.query.all()) == 0


def test_should_not_delete_verification_codes_less_than_one_day_old(sample_user):
    make_verify_code(sample_user, age=timedelta(hours=23, minutes=59, seconds=59), code="12345")
    make_verify_code(sample_user, age=timedelta(hours=24), code="54321")

    assert len(VerifyCode.query.all()) == 2
    delete_codes_older_created_more_than_a_day_ago()
    assert len(VerifyCode.query.all()) == 1
    assert VerifyCode.query.first()._code == "12345"


def make_verify_code(user, age=timedelta(hours=0), code="12335"):
    verify_code = VerifyCode(
        code_type='sms',
        _code=code,
        created_at=datetime.utcnow() - age,
        expiry_datetime=datetime.utcnow(),
        user=user
    )
    db.session.add(verify_code)
    db.session.commit()
