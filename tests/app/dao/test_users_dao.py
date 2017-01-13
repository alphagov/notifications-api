from datetime import datetime, timedelta

from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound
import pytest

from app import db
from app.dao.users_dao import (
    save_model_user,
    save_user_attribute,
    get_user_by_id,
    delete_model_user,
    increment_failed_login_count,
    reset_failed_login_count,
    get_user_by_email,
    delete_codes_older_created_more_than_a_day_ago,
)

from app.models import User, VerifyCode

from tests.app.db import create_user


def test_create_user(notify_db_session):
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


def test_get_all_users(notify_db_session):
    create_user(email='1@test.com')
    create_user(email='2@test.com')

    assert User.query.count() == 2
    assert len(get_user_by_id()) == 2


def test_get_user(notify_db_session):
    email = '1@test.com'
    user = create_user(email=email)
    assert get_user_by_id(user_id=user.id).email_address == email


def test_get_user_not_exists(notify_db_session, fake_uuid):
    with pytest.raises(NoResultFound):
        get_user_by_id(user_id=fake_uuid)


def test_get_user_invalid_id(notify_db_session):
    with pytest.raises(DataError):
        get_user_by_id(user_id="blah")


def test_delete_users(sample_user):
    assert User.query.count() == 1
    delete_model_user(sample_user)
    assert User.query.count() == 0


def test_increment_failed_login_should_increment_failed_logins(sample_user):
    assert sample_user.failed_login_count == 0
    increment_failed_login_count(sample_user)
    assert sample_user.failed_login_count == 1


def test_reset_failed_login_should_set_failed_logins_to_0(sample_user):
    increment_failed_login_count(sample_user)
    assert sample_user.failed_login_count == 1
    reset_failed_login_count(sample_user)
    assert sample_user.failed_login_count == 0


def test_get_user_by_email(sample_user):
    user_from_db = get_user_by_email(sample_user.email_address)
    assert sample_user == user_from_db


def test_get_user_by_email_is_case_insensitive(sample_user):
    email = sample_user.email_address
    user_from_db = get_user_by_email(email.upper())
    assert sample_user == user_from_db


def test_should_delete_all_verification_codes_more_than_one_day_old(sample_user):
    make_verify_code(sample_user, age=timedelta(hours=24), code="54321")
    make_verify_code(sample_user, age=timedelta(hours=24), code="54321")
    assert VerifyCode.query.count() == 2
    delete_codes_older_created_more_than_a_day_ago()
    assert VerifyCode.query.count() == 0


def test_should_not_delete_verification_codes_less_than_one_day_old(sample_user):
    make_verify_code(sample_user, age=timedelta(hours=23, minutes=59, seconds=59), code="12345")
    make_verify_code(sample_user, age=timedelta(hours=24), code="54321")

    assert VerifyCode.query.count() == 2
    delete_codes_older_created_more_than_a_day_ago()
    assert VerifyCode.query.one()._code == "12345"


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


@pytest.mark.parametrize('user_attribute, user_value', [
    ('name', 'New User'),
    ('email_address', 'newuser@mail.com'),
    ('mobile_number', '+4407700900460')
])
def test_update_user_attribute(client, sample_user, user_attribute, user_value):
    assert getattr(sample_user, user_attribute) != user_value
    update_dict = {
        user_attribute: user_value
    }
    save_user_attribute(sample_user, update_dict)
    assert getattr(sample_user, user_attribute) == user_value
