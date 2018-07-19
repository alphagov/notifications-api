import uuid
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.dao.service_data_retention_dao import (
    fetch_service_data_retention,
    insert_service_data_retention,
    update_service_data_retention,
    fetch_service_data_retention_by_id,
    fetch_service_data_retention_by_notification_type
)
from app.models import ServiceDataRetention
from tests.app.db import create_service, create_service_data_retention


def test_fetch_service_data_retention(sample_service):
    email_data_retention = insert_service_data_retention(sample_service.id, 'email', 3)
    letter_data_retention = insert_service_data_retention(sample_service.id, 'letter', 30)
    sms_data_retention = insert_service_data_retention(sample_service.id, 'sms', 5)

    list_of_data_retention = fetch_service_data_retention(sample_service.id)

    assert len(list_of_data_retention) == 3
    assert list_of_data_retention[0] == email_data_retention
    assert list_of_data_retention[1] == sms_data_retention
    assert list_of_data_retention[2] == letter_data_retention


def test_fetch_service_data_retention_only_returns_row_for_service(sample_service):
    another_service = create_service(service_name="Another service")
    email_data_retention = insert_service_data_retention(sample_service.id, 'email', 3)
    letter_data_retention = insert_service_data_retention(sample_service.id, 'letter', 30)
    insert_service_data_retention(another_service.id, 'sms', 5)

    list_of_data_retention = fetch_service_data_retention(sample_service.id)
    assert len(list_of_data_retention) == 2
    assert list_of_data_retention[0] == email_data_retention
    assert list_of_data_retention[1] == letter_data_retention


def test_fetch_service_data_retention_returns_empty_list_when_no_rows_for_service(sample_service):
    empty_list = fetch_service_data_retention(sample_service.id)
    assert not empty_list


def test_fetch_service_data_retention_by_id(sample_service):
    email_data_retention = insert_service_data_retention(sample_service.id, 'email', 3)
    insert_service_data_retention(sample_service.id, 'sms', 13)
    result = fetch_service_data_retention_by_id(sample_service.id, email_data_retention.id)
    assert result == email_data_retention


def test_fetch_service_data_retention_by_id_returns_none_if_not_found(sample_service):
    result = fetch_service_data_retention_by_id(sample_service.id, uuid.uuid4())
    assert not result


def test_fetch_service_data_retention_by_id_returns_none_if_id_not_for_service(sample_service):
    another_service = create_service(service_name="Another service")
    email_data_retention = insert_service_data_retention(sample_service.id, 'email', 3)
    result = fetch_service_data_retention_by_id(another_service.id, email_data_retention.id)
    assert not result


def test_insert_service_data_retention(sample_service):
    insert_service_data_retention(
        service_id=sample_service.id,
        notification_type='email',
        days_of_retention=3
    )

    results = ServiceDataRetention.query.all()
    assert len(results) == 1
    assert results[0].service_id == sample_service.id
    assert results[0].notification_type == 'email'
    assert results[0].days_of_retention == 3
    assert results[0].created_at.date() == datetime.utcnow().date()


def test_insert_service_data_retention_throws_unique_constraint(sample_service):
    insert_service_data_retention(service_id=sample_service.id,
                                  notification_type='email',
                                  days_of_retention=3
                                  )
    with pytest.raises(expected_exception=IntegrityError):
        insert_service_data_retention(service_id=sample_service.id,
                                      notification_type='email',
                                      days_of_retention=5
                                      )


def test_update_service_data_retention(sample_service):
    data_retention = insert_service_data_retention(service_id=sample_service.id,
                                                   notification_type='sms',
                                                   days_of_retention=3
                                                   )
    updated_count = update_service_data_retention(service_data_retention_id=data_retention.id,
                                                  service_id=sample_service.id,
                                                  days_of_retention=5
                                                  )
    assert updated_count == 1
    results = ServiceDataRetention.query.all()
    assert len(results) == 1
    assert results[0].id == data_retention.id
    assert results[0].service_id == sample_service.id
    assert results[0].notification_type == 'sms'
    assert results[0].days_of_retention == 5
    assert results[0].created_at.date() == datetime.utcnow().date()
    assert results[0].updated_at.date() == datetime.utcnow().date()


def test_update_service_data_retention_does_not_update_if_row_does_not_exist(sample_service):
    updated_count = update_service_data_retention(
        service_data_retention_id=uuid.uuid4(),
        service_id=sample_service.id,
        days_of_retention=5
    )
    assert updated_count == 0
    assert len(ServiceDataRetention.query.all()) == 0


def test_update_service_data_retention_does_not_update_row_if_data_retention_is_for_different_service(
        sample_service
):
    data_retention = insert_service_data_retention(service_id=sample_service.id,
                                                   notification_type='email',
                                                   days_of_retention=3
                                                   )
    updated_count = update_service_data_retention(service_data_retention_id=data_retention.id,
                                                  service_id=uuid.uuid4(),
                                                  days_of_retention=5)
    assert updated_count == 0


@pytest.mark.parametrize('notification_type, alternate',
                         [('sms', 'email'),
                          ('email', 'sms'), ('letter', 'email')])
def test_fetch_service_data_retention_by_notification_type(sample_service, notification_type, alternate):
    data_retention = create_service_data_retention(service_id=sample_service.id, notification_type=notification_type)
    create_service_data_retention(service_id=sample_service.id, notification_type=alternate)
    result = fetch_service_data_retention_by_notification_type(sample_service.id, notification_type)
    assert result == data_retention


def test_fetch_service_data_retention_by_notification_type_returns_none_when_no_rows(sample_service):
    assert not fetch_service_data_retention_by_notification_type(sample_service.id, 'email')
