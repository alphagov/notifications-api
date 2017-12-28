from datetime import datetime, timedelta

from freezegun import freeze_time

from app.dao.inbound_sms_dao import (
    dao_get_inbound_sms_for_service,
    dao_count_inbound_sms_for_service,
    delete_inbound_sms_created_more_than_a_week_ago,
    dao_get_inbound_sms_by_id,
    dao_get_paginated_inbound_sms_for_service
)
from tests.app.db import create_inbound_sms, create_service

from app.models import InboundSms


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
        create_inbound_sms(sample_service)
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
    create_inbound_sms(service_two)

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


@freeze_time("2017-01-01 12:00:00")
def test_should_delete_inbound_sms_older_than_seven_days(sample_service):
    older_than_seven_days = datetime.utcnow() - timedelta(days=7, seconds=1)
    create_inbound_sms(sample_service, created_at=older_than_seven_days)
    delete_inbound_sms_created_more_than_a_week_ago()

    assert len(InboundSms.query.all()) == 0


@freeze_time("2017-01-01 12:00:00")
def test_should_not_delete_inbound_sms_before_seven_days(sample_service):
    yesterday = datetime.utcnow() - timedelta(days=1)
    just_before_seven_days = datetime.utcnow() - timedelta(days=6, hours=23, minutes=59, seconds=59)
    older_than_seven_days = datetime.utcnow() - timedelta(days=7, seconds=1)

    create_inbound_sms(sample_service, created_at=yesterday)
    create_inbound_sms(sample_service, created_at=just_before_seven_days)
    create_inbound_sms(sample_service, created_at=older_than_seven_days)

    delete_inbound_sms_created_more_than_a_week_ago()

    assert len(InboundSms.query.all()) == 2


def test_get_inbound_sms_by_id_returns(sample_service):
    inbound_sms = create_inbound_sms(service=sample_service)
    inbound_from_db = dao_get_inbound_sms_by_id(inbound_sms.service.id, inbound_sms.id)

    assert inbound_sms == inbound_from_db


def test_dao_get_paginated_inbound_sms_for_service(sample_service):
    inbound_sms = create_inbound_sms(service=sample_service)
    inbound_from_db = dao_get_paginated_inbound_sms_for_service(inbound_sms.service.id)

    assert inbound_sms == inbound_from_db[0]


def test_dao_get_paginated_inbound_sms_for_service_return_only_for_service(sample_service):
    inbound_sms = create_inbound_sms(service=sample_service)
    another_service = create_service(service_name='another service')
    another_inbound_sms = create_inbound_sms(another_service)

    inbound_from_db = dao_get_paginated_inbound_sms_for_service(inbound_sms.service.id)

    assert inbound_sms in inbound_from_db
    assert another_inbound_sms not in inbound_from_db


def test_dao_get_paginated_inbound_sms_for_service_no_inbound_sms_returns_empty_list(sample_service):
    inbound_from_db = dao_get_paginated_inbound_sms_for_service(sample_service.id)

    assert inbound_from_db == []


def test_dao_get_paginated_inbound_sms_for_service_page_size_returns_correct_size(sample_service):
    inbound_sms_list = [
        create_inbound_sms(sample_service),
        create_inbound_sms(sample_service),
        create_inbound_sms(sample_service),
        create_inbound_sms(sample_service),
    ]
    reversed_inbound_sms = sorted(inbound_sms_list, key=lambda sms: sms.created_at, reverse=True)

    inbound_from_db = dao_get_paginated_inbound_sms_for_service(
        sample_service.id,
        older_than=reversed_inbound_sms[1].id,
        page_size=2
    )

    assert len(inbound_from_db) == 2


def test_dao_get_paginated_inbound_sms_for_service_older_than_returns_correct_list(sample_service):
    inbound_sms_list = [
        create_inbound_sms(sample_service),
        create_inbound_sms(sample_service),
        create_inbound_sms(sample_service),
        create_inbound_sms(sample_service),
    ]
    reversed_inbound_sms = sorted(inbound_sms_list, key=lambda sms: sms.created_at, reverse=True)

    inbound_from_db = dao_get_paginated_inbound_sms_for_service(
        sample_service.id,
        older_than=reversed_inbound_sms[1].id,
        page_size=2
    )

    expected_inbound_sms = reversed_inbound_sms[2:]

    assert expected_inbound_sms == inbound_from_db


def test_dao_get_paginated_inbound_sms_for_service_older_than_end_returns_empty_list(sample_service):
    inbound_sms_list = [
        create_inbound_sms(sample_service),
        create_inbound_sms(sample_service),
    ]
    reversed_inbound_sms = sorted(inbound_sms_list, key=lambda sms: sms.created_at, reverse=True)

    inbound_from_db = dao_get_paginated_inbound_sms_for_service(
        sample_service.id,
        older_than=reversed_inbound_sms[1].id,
        page_size=2
    )

    assert inbound_from_db == []
