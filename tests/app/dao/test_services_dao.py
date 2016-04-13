import uuid
import pytest
from app.dao.services_dao import (
    dao_create_service,
    dao_add_user_to_service,
    dao_remove_user_from_service,
    dao_fetch_all_services,
    dao_fetch_service_by_id,
    dao_fetch_all_services_by_user,
    dao_fetch_service_by_id_and_user
)
from app.dao.users_dao import save_model_user
from app.models import Service, User
from sqlalchemy.orm.exc import FlushError, NoResultFound
from sqlalchemy.exc import IntegrityError


def test_create_service(sample_user):
    assert Service.query.count() == 0
    service = Service(name="service_name", email_from="email_from", message_limit=1000, active=True, restricted=False)
    dao_create_service(service, sample_user)
    assert Service.query.count() == 1
    assert Service.query.first().name == "service_name"
    assert Service.query.first().id == service.id
    assert sample_user in Service.query.first().users


def test_cannot_create_two_services_with_same_name(sample_user):
    assert Service.query.count() == 0
    service1 = Service(name="service_name", email_from="email_from1", message_limit=1000, active=True, restricted=False)
    service2 = Service(name="service_name", email_from="email_from2", message_limit=1000, active=True, restricted=False)
    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service1, sample_user)
        dao_create_service(service2, sample_user)
    assert 'duplicate key value violates unique constraint "services_name_key"' in str(excinfo.value)


def test_cannot_create_two_services_with_same_email_from(sample_user):
    assert Service.query.count() == 0
    service1 = Service(name="service_name1", email_from="email_from", message_limit=1000, active=True, restricted=False)
    service2 = Service(name="service_name2", email_from="email_from", message_limit=1000, active=True, restricted=False)
    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service1, sample_user)
        dao_create_service(service2, sample_user)
    assert 'duplicate key value violates unique constraint "services_email_from_key"' in str(excinfo.value)


def test_cannot_create_service_with_no_user(notify_db_session):
    assert Service.query.count() == 0
    service = Service(name="service_name", email_from="email_from", message_limit=1000, active=True, restricted=False)
    with pytest.raises(FlushError) as excinfo:
        dao_create_service(service, None)
    assert "Can't flush None value found in collection Service.users" in str(excinfo.value)


def test_should_add_user_to_service(sample_user):
    service = Service(name="service_name", email_from="email_from", message_limit=1000, active=True, restricted=False)
    dao_create_service(service, sample_user)
    assert sample_user in Service.query.first().users
    new_user = User(
        name='Test User',
        email_address='new_user@digital.cabinet-office.gov.uk',
        password='password',
        mobile_number='+447700900986'
    )
    save_model_user(new_user)
    dao_add_user_to_service(service, new_user)
    assert new_user in Service.query.first().users


def test_should_remove_user_from_service(sample_user):
    service = Service(name="service_name", email_from="email_from", message_limit=1000, active=True, restricted=False)
    dao_create_service(service, sample_user)
    new_user = User(
        name='Test User',
        email_address='new_user@digital.cabinet-office.gov.uk',
        password='password',
        mobile_number='+447700900986'
    )
    save_model_user(new_user)
    dao_add_user_to_service(service, new_user)
    assert new_user in Service.query.first().users
    dao_remove_user_from_service(service, new_user)
    assert new_user not in Service.query.first().users


def test_get_all_services(service_factory):
    service_factory.get('service 1', email_from='service.1')
    assert len(dao_fetch_all_services()) == 1
    assert dao_fetch_all_services()[0].name == 'service 1'

    service_factory.get('service 2', email_from='service.2')
    assert len(dao_fetch_all_services()) == 2
    assert dao_fetch_all_services()[1].name == 'service 2'


def test_get_all_services_should_return_in_created_order(service_factory):
    service_factory.get('service 1', email_from='service.1')
    service_factory.get('service 2', email_from='service.2')
    service_factory.get('service 3', email_from='service.3')
    service_factory.get('service 4', email_from='service.4')
    assert len(dao_fetch_all_services()) == 4
    assert dao_fetch_all_services()[0].name == 'service 1'
    assert dao_fetch_all_services()[1].name == 'service 2'
    assert dao_fetch_all_services()[2].name == 'service 3'
    assert dao_fetch_all_services()[3].name == 'service 4'


def test_get_all_services_should_return_empty_list_if_no_services():
    assert len(dao_fetch_all_services()) == 0


def test_get_all_services_for_user(service_factory, sample_user):
    service_factory.get('service 1', sample_user, email_from='service.1')
    service_factory.get('service 2', sample_user, email_from='service.2')
    service_factory.get('service 3', sample_user, email_from='service.3')
    assert len(dao_fetch_all_services_by_user(sample_user.id)) == 3
    assert dao_fetch_all_services_by_user(sample_user.id)[0].name == 'service 1'
    assert dao_fetch_all_services_by_user(sample_user.id)[1].name == 'service 2'
    assert dao_fetch_all_services_by_user(sample_user.id)[2].name == 'service 3'


def test_get_all_only_services_user_has_access_to(service_factory, sample_user):
    service_factory.get('service 1', sample_user, email_from='service.1')
    service_factory.get('service 2', sample_user, email_from='service.2')
    service_3 = service_factory.get('service 3', sample_user, email_from='service.3')
    new_user = User(
        name='Test User',
        email_address='new_user@digital.cabinet-office.gov.uk',
        password='password',
        mobile_number='+447700900986'
    )
    save_model_user(new_user)
    dao_add_user_to_service(service_3, new_user)
    assert len(dao_fetch_all_services_by_user(sample_user.id)) == 3
    assert dao_fetch_all_services_by_user(sample_user.id)[0].name == 'service 1'
    assert dao_fetch_all_services_by_user(sample_user.id)[1].name == 'service 2'
    assert dao_fetch_all_services_by_user(sample_user.id)[2].name == 'service 3'
    assert len(dao_fetch_all_services_by_user(new_user.id)) == 1
    assert dao_fetch_all_services_by_user(new_user.id)[0].name == 'service 3'


def test_get_all_user_services_should_return_empty_list_if_no_services_for_user(sample_user):
    assert len(dao_fetch_all_services_by_user(sample_user.id)) == 0


def test_get_service_by_id_returns_none_if_no_service(notify_db):
    with pytest.raises(NoResultFound) as e:
        dao_fetch_service_by_id(str(uuid.uuid4()))
    assert 'No row was found for one()' in str(e)


def test_get_service_by_id_returns_service(service_factory):
    service = service_factory.get('testing', email_from='testing')
    assert dao_fetch_service_by_id(service.id).name == 'testing'


def test_can_get_service_by_id_and_user(service_factory, sample_user):
    service = service_factory.get('service 1', sample_user, email_from='service.1')
    assert dao_fetch_service_by_id_and_user(service.id, sample_user.id).name == 'service 1'


def test_cannot_get_service_by_id_and_owned_by_different_user(service_factory, sample_user):
    service1 = service_factory.get('service 1', sample_user, email_from='service.1')
    new_user = User(
        name='Test User',
        email_address='new_user@digital.cabinet-office.gov.uk',
        password='password',
        mobile_number='+447700900986'
    )
    save_model_user(new_user)
    service2 = service_factory.get('service 2', new_user, email_from='service.2')
    assert dao_fetch_service_by_id_and_user(service1.id, sample_user.id).name == 'service 1'
    with pytest.raises(NoResultFound) as e:
        dao_fetch_service_by_id_and_user(service2.id, sample_user.id)
    assert 'No row was found for one()' in str(e)
