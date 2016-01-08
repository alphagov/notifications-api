from app.main.dao.users_dao import (create_user, get_users)
from tests.app.conftest import sample_user as create_sample_user
from app.models import User


def test_create_user(notify_api, notify_db, notify_db_session):
    email = 'notify@digital.cabinet-office.gov.uk'
    user_id = create_user(email)
    assert User.query.count() == 1
    assert User.query.first().email_address == email
    assert User.query.filter_by(id=user_id).one()


def test_get_all_users(notify_api, notify_db, notify_db_session, sample_user):
    assert User.query.count() == 1
    assert len(get_users()) == 1
    email = "another.notify@digital.cabinet-office.gov.uk"
    another_user = create_sample_user(notify_db,
                                      notify_db_session,
                                      email=email)
    assert User.query.count() == 2
    assert len(get_users()) == 2


def test_get_user(notify_api, notify_db, notify_db_session):
    email = "another.notify@digital.cabinet-office.gov.uk"
    another_user = create_sample_user(notify_db,
                                      notify_db_session,
                                      email=email)
    assert get_users(user_id=another_user.id).email_address == email
