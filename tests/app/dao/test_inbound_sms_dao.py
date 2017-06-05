from datetime import datetime

from freezegun import freeze_time

from app.dao.inbound_sms_dao import dao_get_inbound_sms_for_service, dao_count_inbound_sms_for_service

from tests.app.db import create_inbound_sms, create_service


def test_get_all_inbound_sms(sample_service):
    inbound = create_inbound_sms(sample_service)

    res = dao_get_inbound_sms_for_service(sample_service.id)
    assert len(res) == 1
    assert res[0] == inbound


def test_get_all_inbound_sms_when_none_exist(sample_service):
    res = dao_get_inbound_sms_for_service(sample_service.id)
    assert len(res) == 0


def test_get_all_inbound_sms_limits_and_orders(sample_service):
    with freeze_time('2017-01-01'):
        one = create_inbound_sms(sample_service)
    with freeze_time('2017-01-03'):
        three = create_inbound_sms(sample_service)
    with freeze_time('2017-01-02'):
        two = create_inbound_sms(sample_service)

    res = dao_get_inbound_sms_for_service(sample_service.id, limit=2)
    assert len(res) == 2
    assert res[0] == three
    assert res[0].created_at == datetime(2017, 1, 3)
    assert res[1] == two
    assert res[1].created_at == datetime(2017, 1, 2)


def test_get_all_inbound_sms_filters_on_service(notify_db_session):
    service_one = create_service(service_name='one')
    service_two = create_service(service_name='two')

    sms_one = create_inbound_sms(service_one)
    sms_two = create_inbound_sms(service_two)

    res = dao_get_inbound_sms_for_service(service_one.id)
    assert len(res) == 1
    assert res[0] == sms_one


def test_count_inbound_sms_for_service(notify_db_session):
    service_one = create_service(service_name='one')
    service_two = create_service(service_name='two')

    create_inbound_sms(service_one)
    create_inbound_sms(service_one)
    create_inbound_sms(service_two)

    assert dao_count_inbound_sms_for_service(service_one.id) == 2
