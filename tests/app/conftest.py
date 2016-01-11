import pytest
from app.models import (User, Service)
from app.dao.users_dao import (create_model_user, get_model_users)
from app.dao.services_dao import create_model_service


@pytest.fixture(scope='function')
def sample_user(notify_db,
                notify_db_session,
                email="notify@digital.cabinet-office.gov.uk"):
    user = User(**{'email_address': email})
    create_model_user(user)
    return user


@pytest.fixture(scope='function')
def sample_service(notify_db,
                   notify_db_session,
                   service_name="Sample service",
                   user=None):
    if user is None:
        user = sample_user(notify_db, notify_db_session)
    data = {
        'name': service_name,
        'users': [user],
        'limit': 1000,
        'active': False,
        'restricted': False}
    service = Service(**data)
    create_model_service(service)
    return service
