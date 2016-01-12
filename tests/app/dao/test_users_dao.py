from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound
from app.dao.users_dao import (
    save_model_user, get_model_users, delete_model_user)
from tests.app.conftest import sample_user as create_sample_user
from app.models import User


def test_create_user(notify_api, notify_db, notify_db_session):
    email = 'notify@digital.cabinet-office.gov.uk'
    user = User(**{'email_address': email})
    save_model_user(user)
    assert User.query.count() == 1
    assert User.query.first().email_address == email
    assert User.query.first().id == user.id


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
    except:
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
