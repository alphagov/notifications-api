import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import signing
from app.constants import ServiceCallbackTypes
from app.dao.service_callback_api_dao import (
    get_delivery_status_callback_api_for_service,
    get_returned_letter_callback_api_for_service,
    get_service_callback_api,
    reset_service_callback_api,
    save_service_callback_api,
)
from app.models import ServiceCallbackApi
from tests.app.db import create_service_callback_api


@pytest.mark.parametrize(
    "callback_type",
    [
        ServiceCallbackTypes.inbound_sms.value,
        ServiceCallbackTypes.delivery_status.value,
        ServiceCallbackTypes.returned_letter.value,
    ],
)
def test_save_service_callback_api(sample_service, callback_type):
    service_callback_api = ServiceCallbackApi(
        service_id=sample_service.id,
        url=f"https://some_service/{callback_type}",
        bearer_token=f"some_unique_string_{callback_type}",
        updated_by_id=sample_service.users[0].id,
        callback_type=callback_type,
    )

    save_service_callback_api(service_callback_api)

    results = ServiceCallbackApi.query.all()
    assert len(results) == 1
    callback_api = results[0]
    assert callback_api.id is not None
    assert callback_api.service_id == sample_service.id
    assert callback_api.updated_by_id == sample_service.users[0].id
    assert callback_api.url == f"https://some_service/{callback_type}"
    assert callback_api.bearer_token == f"some_unique_string_{callback_type}"
    assert callback_api._bearer_token != f"some_unique_string_{callback_type}"
    assert callback_api.updated_at is None

    versioned = ServiceCallbackApi.get_history_model().query.filter_by(id=callback_api.id).one()
    assert versioned.id == callback_api.id
    assert versioned.service_id == sample_service.id
    assert versioned.updated_by_id == sample_service.users[0].id
    assert versioned.url == f"https://some_service/{callback_type}"
    # note that on the history model, the attribute name matches the column name (and stores the encoded version)
    assert signing.decode(versioned.bearer_token) == f"some_unique_string_{callback_type}"
    assert versioned.updated_at is None
    assert versioned.version == 1


@pytest.mark.parametrize(
    "callback_type",
    [
        ServiceCallbackTypes.inbound_sms.value,
        ServiceCallbackTypes.delivery_status.value,
        ServiceCallbackTypes.returned_letter.value,
    ],
)
def test_save_service_callback_api_fails_if_service_does_not_exist(notify_db_session, callback_type):
    service_callback_api = ServiceCallbackApi(
        service_id=uuid.uuid4(),
        url="https://some_service/callback_endpoint",
        bearer_token="some_unique_string",
        updated_by_id=uuid.uuid4(),
        callback_type=callback_type,
    )

    with pytest.raises(SQLAlchemyError):
        save_service_callback_api(service_callback_api)


@pytest.mark.parametrize(
    "callback_type",
    [
        ServiceCallbackTypes.inbound_sms.value,
        ServiceCallbackTypes.delivery_status.value,
        ServiceCallbackTypes.returned_letter.value,
    ],
)
def test_update_service_callback_api_unique_constraint(sample_service, callback_type):
    service_callback_api = ServiceCallbackApi(
        service_id=sample_service.id,
        url=f"https://some_service/{callback_type}",
        bearer_token="some_unique_string",
        updated_by_id=sample_service.users[0].id,
        callback_type=callback_type,
    )
    save_service_callback_api(service_callback_api)
    another = ServiceCallbackApi(
        service_id=sample_service.id,
        url=f"https://some_service/{callback_type}",
        bearer_token="different_string",
        updated_by_id=sample_service.users[0].id,
        callback_type=callback_type,
    )
    with pytest.raises(expected_exception=SQLAlchemyError):
        save_service_callback_api(another)


@pytest.mark.parametrize(
    "callback_type",
    [
        ServiceCallbackTypes.inbound_sms.value,
        ServiceCallbackTypes.delivery_status.value,
        ServiceCallbackTypes.returned_letter.value,
    ],
)
def test_update_service_callback_can_add_two_api_of_different_types(sample_service, callback_type):
    callback_api = ServiceCallbackApi(
        service_id=sample_service.id,
        url="https://some_service/callback_endpoint",
        bearer_token="some_unique_string",
        updated_by_id=sample_service.users[0].id,
        callback_type=callback_type,
    )
    save_service_callback_api(callback_api)
    complaint = ServiceCallbackApi(
        service_id=sample_service.id,
        url=f"https://some_service/{callback_type}",
        bearer_token="different_string",
        updated_by_id=sample_service.users[0].id,
        callback_type="complaint",
    )
    save_service_callback_api(complaint)
    results = ServiceCallbackApi.query.order_by(ServiceCallbackApi.callback_type).all()
    assert len(results) == 2
    assert results[0].serialize() == complaint.serialize()
    assert results[1].serialize() == callback_api.serialize()


@pytest.mark.parametrize(
    "callback_type",
    [
        ServiceCallbackTypes.inbound_sms.value,
        ServiceCallbackTypes.delivery_status.value,
        ServiceCallbackTypes.returned_letter.value,
    ],
)
def test_update_service_callback_api(sample_service, callback_type):
    service_callback_api = ServiceCallbackApi(
        service_id=sample_service.id,
        url=f"https://some_service/{callback_type}",
        bearer_token=f"some_unique_string_{callback_type}",
        updated_by_id=sample_service.users[0].id,
        callback_type=callback_type,
    )

    save_service_callback_api(service_callback_api)
    results = ServiceCallbackApi.query.all()
    assert len(results) == 1
    saved_callback_api = results[0]

    reset_service_callback_api(
        saved_callback_api, updated_by_id=sample_service.users[0].id, url="https://some_service/changed_url"
    )
    updated_results = ServiceCallbackApi.query.all()
    assert len(updated_results) == 1
    updated = updated_results[0]
    assert updated.id is not None
    assert updated.service_id == sample_service.id
    assert updated.updated_by_id == sample_service.users[0].id
    assert updated.url == "https://some_service/changed_url"
    assert updated.bearer_token == f"some_unique_string_{callback_type}"
    assert updated._bearer_token != f"some_unique_string_{callback_type}"
    assert updated.updated_at is not None

    versioned_results = ServiceCallbackApi.get_history_model().query.filter_by(id=saved_callback_api.id).all()
    assert len(versioned_results) == 2
    for x in versioned_results:
        if x.version == 1:
            assert x.url == f"https://some_service/{callback_type}"
            assert not x.updated_at
        elif x.version == 2:
            assert x.url == "https://some_service/changed_url"
            assert x.updated_at
        else:
            pytest.fail("version should not exist")
        assert x.id is not None
        assert x.service_id == sample_service.id
        assert x.updated_by_id == sample_service.users[0].id
        assert signing.decode(x.bearer_token) == f"some_unique_string_{callback_type}"


@pytest.mark.parametrize(
    "callback_type",
    [
        ServiceCallbackTypes.inbound_sms.value,
        ServiceCallbackTypes.delivery_status.value,
        ServiceCallbackTypes.returned_letter.value,
    ],
)
def test_get_service_callback_api(sample_service, callback_type):
    callback_api = ServiceCallbackApi(
        service_id=sample_service.id,
        url=f"https://some_service/{callback_type}",
        bearer_token=f"{callback_type}_unique_string",
        updated_by_id=sample_service.users[0].id,
        callback_type=callback_type,
    )
    save_service_callback_api(callback_api)

    service_complaint_callback_api = ServiceCallbackApi(
        service_id=sample_service.id,
        url="https://some_service/complaint_callback_endpoint",
        bearer_token="complaint_unique_string",
        updated_by_id=sample_service.users[0].id,
        callback_type=ServiceCallbackTypes.complaint.value,
    )
    save_service_callback_api(service_complaint_callback_api)

    callback_api = get_service_callback_api(callback_api.id, sample_service.id, callback_type)
    assert callback_api.id is not None
    assert callback_api.service_id == sample_service.id
    assert callback_api.updated_by_id == sample_service.users[0].id
    assert callback_api.url == f"https://some_service/{callback_type}"
    assert callback_api.bearer_token == f"{callback_type}_unique_string"
    assert callback_api._bearer_token != f"{callback_type}_unique_string"
    assert callback_api.updated_at is None

    complaint_callback_api = get_service_callback_api(
        service_complaint_callback_api.id, sample_service.id, ServiceCallbackTypes.complaint.value
    )
    assert complaint_callback_api.id is not None
    assert complaint_callback_api.service_id == sample_service.id
    assert complaint_callback_api.updated_by_id == sample_service.users[0].id
    assert complaint_callback_api.url == "https://some_service/complaint_callback_endpoint"
    assert complaint_callback_api.bearer_token == "complaint_unique_string"
    assert complaint_callback_api._bearer_token != "complaint_unique_string"
    assert complaint_callback_api.updated_at is None


def test_get_delivery_status_callback_api_for_service(sample_service):
    service_callback_api = create_service_callback_api(callback_type="delivery_status", service=sample_service)
    result = get_delivery_status_callback_api_for_service(sample_service.id)
    assert result.id == service_callback_api.id
    assert result.url == service_callback_api.url
    assert result.bearer_token == service_callback_api.bearer_token
    assert result.created_at == service_callback_api.created_at
    assert result.updated_at == service_callback_api.updated_at
    assert result.updated_by_id == service_callback_api.updated_by_id


def test_get_returned_letter_callback_api_for_service(sample_service):
    service_callback_api = create_service_callback_api(callback_type="returned_letter", service=sample_service)
    result = get_returned_letter_callback_api_for_service(sample_service.id)
    assert result.id == service_callback_api.id
    assert result.url == service_callback_api.url
    assert result.bearer_token == service_callback_api.bearer_token
    assert result.created_at == service_callback_api.created_at
    assert result.updated_at == service_callback_api.updated_at
    assert result.updated_by_id == service_callback_api.updated_by_id
