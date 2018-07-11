import uuid
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.dao.service_data_retention_dao import insert_service_data_retention, update_service_data_retention
from app.models import ServiceDataRetention


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
