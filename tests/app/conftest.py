import pytest
from app.dao.users_dao import (create_user, get_users)
from app.dao.services_dao import (create_service, get_services)


@pytest.fixture(scope='function')
def sample_user(notify_db,
                notify_db_session,
                email="notify@digital.cabinet-office.gov.uk"):
    user_id = create_user(email)
    return get_users(user_id=user_id)


@pytest.fixture(scope='function')
def sample_service(notify_db,
                   notify_db_session,
                   service_name="Sample service",
                   user=None):
    if user is None:
        user = sample_user(notify_db, notify_db_session)
    service_id = create_service(service_name, user)
    return get_services(service_id=service_id)
