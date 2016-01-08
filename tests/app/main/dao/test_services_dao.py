from app.main.dao.services_dao import (create_service, get_services)
from tests.app.conftest import sample_service as create_sample_service
from app.models import Service


def test_create_service(notify_api, notify_db, notify_db_session, sample_user):
    assert Service.query.count() == 0
    service_name = 'Sample Service'
    service_id = create_service(service_name, sample_user)
    assert Service.query.count() == 1
    assert Service.query.first().name == service_name
    assert Service.query.first().id == service_id


def test_get_services(notify_api, notify_db, notify_db_session, sample_user):
    sample_service = create_sample_service(notify_db,
                                           notify_db_session,
                                           user=sample_user)
    assert Service.query.count() == 1
    assert len(get_services()) == 1
    service_name = "Another service"
    sample_service = create_sample_service(notify_db,
                                           notify_db_session,
                                           service_name=service_name,
                                           user=sample_user)
    assert Service.query.count() == 2
    assert len(get_services()) == 2


def test_get_user_service(notify_api, notify_db, notify_db_session, sample_user):
    assert Service.query.count() == 0
    service_name = "Random service"
    sample_service = create_sample_service(notify_db,
                                           notify_db_session,
                                           service_name=service_name,
                                           user=sample_user)
    assert get_services(service_id=sample_service.id).name == service_name
    assert Service.query.count() == 1
