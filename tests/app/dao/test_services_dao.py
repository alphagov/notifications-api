import pytest
from app.dao.services_dao import (
    save_model_service, get_model_services, DAOException, delete_model_service)
from tests.app.conftest import sample_service as create_sample_service
from app.models import Service


def test_create_service(notify_api, notify_db, notify_db_session, sample_user):
    assert Service.query.count() == 0
    service_name = 'Sample Service'
    data = {
        'name': service_name,
        'users': [sample_user],
        'limit': 1000,
        'active': False,
        'restricted': False}
    service = Service(**data)
    save_model_service(service)
    assert Service.query.count() == 1
    assert Service.query.first().name == service_name
    assert Service.query.first().id == service.id


def test_get_services(notify_api, notify_db, notify_db_session, sample_user):
    sample_service = create_sample_service(notify_db,
                                           notify_db_session,
                                           user=sample_user)
    assert Service.query.count() == 1
    assert len(get_model_services()) == 1
    service_name = "Another service"
    sample_service = create_sample_service(notify_db,
                                           notify_db_session,
                                           service_name=service_name,
                                           user=sample_user)
    assert Service.query.count() == 2
    assert len(get_model_services()) == 2


def test_get_user_service(notify_api, notify_db, notify_db_session, sample_user):
    assert Service.query.count() == 0
    service_name = "Random service"
    sample_service = create_sample_service(notify_db,
                                           notify_db_session,
                                           service_name=service_name,
                                           user=sample_user)
    assert get_model_services(service_id=sample_service.id).name == service_name
    assert Service.query.count() == 1


def test_missing_user_attribute(notify_api, notify_db, notify_db_session):
    assert Service.query.count() == 0
    try:
        service_name = 'Sample Service'
        data = {
            'name': service_name,
            'limit': 1000,
            'active': False,
            'restricted': False}

        service = Service(**data)
        save_model_service(service)
        pytest.fail("DAOException not thrown")
    except DAOException as e:
        assert "Missing data for required attribute" in str(e)


def test_delete_service(notify_api, notify_db, notify_db_session, sample_service):
    assert Service.query.count() == 1
    delete_model_service(sample_service)
    assert Service.query.count() == 0
