import uuid

import pytest

from app.constants import ServiceCallbackTypes
from app.models import ServiceCallbackApi, ServiceInboundApi
from tests.app.db import create_service_callback_api, create_service_inbound_api


@pytest.mark.parametrize(
    "callback_type, path",
    [
        (ServiceCallbackTypes.inbound_sms.value, "inbound-sms"),
        (ServiceCallbackTypes.delivery_status.value, "delivery-status"),
        (ServiceCallbackTypes.returned_letter.value, "returned-letter"),
    ],
)
def test_create_service_callback_api(admin_request, sample_service, callback_type, path):
    data = {
        "url": f"https://some_service/{path}",
        "bearer_token": "some-unique-string",
        "updated_by_id": str(sample_service.users[0].id),
        "callback_type": callback_type,
    }
    resp_json = admin_request.post(
        "service_callback.create_service_callback_api", service_id=sample_service.id, _data=data, _expected_status=201
    )

    resp_json = resp_json["data"]
    assert resp_json["id"]
    assert resp_json["service_id"] == str(sample_service.id)
    assert resp_json["url"] == f"https://some_service/{path}"
    assert resp_json["updated_by_id"] == str(sample_service.users[0].id)
    assert resp_json["created_at"]
    assert not resp_json["updated_at"]


@pytest.mark.parametrize(
    "callback_type, path",
    [
        (ServiceCallbackTypes.inbound_sms.value, "inbound-sms"),
        (ServiceCallbackTypes.delivery_status.value, "delivery-status"),
        (ServiceCallbackTypes.returned_letter.value, "returned-letter"),
    ],
)
def test_set_service_callback_api_raises_404_when_service_does_not_exist(admin_request, callback_type, path):
    data = {
        "url": f"https://some_service/{path}",
        "bearer_token": "some-unique-string",
        "updated_by_id": str(uuid.uuid4()),
        "callback_type": callback_type,
    }
    response = admin_request.post(
        "service_callback.create_service_callback_api", service_id=uuid.uuid4(), _data=data, _expected_status=404
    )
    assert response["message"] == "No result found"


@pytest.mark.parametrize(
    "callback_type, path",
    [
        (ServiceCallbackTypes.inbound_sms.value, "inbound-sms"),
        (
            ServiceCallbackTypes.delivery_status.value,
            "delivery-status",
        ),
        (ServiceCallbackTypes.returned_letter.value, "returned-letter"),
    ],
)
def test_update_service_callback_api_updates_url(admin_request, sample_service, callback_type, path):
    if callback_type == ServiceCallbackTypes.inbound_sms.value:
        callback_api = create_service_inbound_api(service=sample_service, url="https://original_url.com")
    else:
        callback_api = create_service_callback_api(
            callback_type=callback_type, service=sample_service, url="https://original_url.com"
        )
    new_url = f"https://another_url.com/{path}"
    data = {"url": new_url, "updated_by_id": str(sample_service.users[0].id), "callback_type": callback_type}

    response = admin_request.post(
        "service_callback.update_service_callback_api",
        service_id=sample_service.id,
        callback_api_id=callback_api.id,
        _data=data,
    )

    assert response["data"]["url"] == new_url
    assert callback_api.url == new_url


@pytest.mark.parametrize(
    "callback_type, path",
    [
        (ServiceCallbackTypes.inbound_sms.value, "inbound-sms"),
        (ServiceCallbackTypes.delivery_status.value, "delivery-status"),
        (ServiceCallbackTypes.returned_letter.value, "returned-letter"),
    ],
)
def test_update_service_callback_api_updates_bearer_token(admin_request, sample_service, callback_type, path):
    if callback_type == ServiceCallbackTypes.inbound_sms.value:
        callback_api = create_service_inbound_api(service=sample_service, url="https://original_url.com")
    else:
        callback_api = create_service_callback_api(
            callback_type=callback_type, service=sample_service, bearer_token=f"some_{callback_type}super_secret"
        )
    data = {
        "bearer_token": f"different_token_{callback_type}",
        "updated_by_id": str(sample_service.users[0].id),
        "callback_type": callback_type,
    }

    admin_request.post(
        "service_callback.update_service_callback_api",
        service_id=sample_service.id,
        callback_api_id=callback_api.id,
        _data=data,
    )
    assert callback_api.bearer_token == f"different_token_{callback_type}"


def test_fetch_service_inbound_api(admin_request, sample_service):
    service_inbound_api = create_service_inbound_api(service=sample_service)

    response = admin_request.get(
        "service_callback.fetch_service_inbound_api",
        service_id=sample_service.id,
        inbound_api_id=service_inbound_api.id,
    )
    assert response["data"] == service_inbound_api.serialize()


def test_delete_service_inbound_api(admin_request, sample_service):
    service_inbound_api = create_service_inbound_api(sample_service)

    response = admin_request.delete(
        "service_callback.remove_service_inbound_api",
        service_id=sample_service.id,
        inbound_api_id=service_inbound_api.id,
    )

    assert response is None
    assert ServiceInboundApi.query.count() == 0


def test_update_delivery_receipt_callback_api_updates_url(admin_request, sample_service):
    service_callback_api = create_service_callback_api(
        callback_type="delivery_status", service=sample_service, url="https://original_url.com"
    )

    data = {"url": "https://another_url.com", "updated_by_id": str(sample_service.users[0].id)}

    resp_json = admin_request.post(
        "service_callback.update_delivery_receipt_callback_api",
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
        _data=data,
    )
    assert resp_json["data"]["url"] == "https://another_url.com"
    assert service_callback_api.url == "https://another_url.com"


def test_update_delivery_receipt_callback_api_updates_bearer_token(admin_request, sample_service):
    service_callback_api = create_service_callback_api(
        callback_type="delivery_status", service=sample_service, bearer_token="some_super_secret"
    )
    data = {"bearer_token": "different_token", "updated_by_id": str(sample_service.users[0].id)}

    admin_request.post(
        "service_callback.update_delivery_receipt_callback_api",
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
        _data=data,
    )
    assert service_callback_api.bearer_token == "different_token"


def test_fetch_delivery_receipt_callback_api(admin_request, sample_service):
    service_callback_api = create_service_callback_api(callback_type="delivery_status", service=sample_service)

    response = admin_request.get(
        "service_callback.fetch_delivery_receipt_callback_api",
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
    )

    assert response["data"] == service_callback_api.serialize()


def test_delete_delivery_receipt_callback_api(admin_request, sample_service):
    service_callback_api = create_service_callback_api("delivery_status", sample_service)

    response = admin_request.delete(
        "service_callback.remove_delivery_receipt_callback_api",
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
    )

    assert response is None
    assert ServiceCallbackApi.query.count() == 0


def test_update_returned_letter_callback_api_updates_url(admin_request, sample_service):
    service_callback_api = create_service_callback_api(
        callback_type="returned_letter", service=sample_service, url="https://original_url.com"
    )

    data = {"url": "https://another_url.com", "updated_by_id": str(sample_service.users[0].id)}

    resp_json = admin_request.post(
        "service_callback.update_returned_letter_callback_api",
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
        _data=data,
    )
    assert resp_json["data"]["url"] == "https://another_url.com"
    assert service_callback_api.url == "https://another_url.com"


def test_update_returned_letter_callback_api_updates_bearer_token(admin_request, sample_service):
    service_callback_api = create_service_callback_api(
        callback_type="returned_letter", service=sample_service, bearer_token="some_super_secret"
    )
    data = {"bearer_token": "different_token", "updated_by_id": str(sample_service.users[0].id)}

    admin_request.post(
        "service_callback.update_returned_letter_callback_api",
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
        _data=data,
    )
    assert service_callback_api.bearer_token == "different_token"


def test_fetch_returned_letter_callback_api(admin_request, sample_service):
    service_callback_api = create_service_callback_api(callback_type="returned_letter", service=sample_service)

    response = admin_request.get(
        "service_callback.fetch_returned_letter_callback_api",
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
    )

    assert response["data"] == service_callback_api.serialize()


def test_delete_returned_letter_callback_api(admin_request, sample_service):
    service_callback_api = create_service_callback_api(callback_type="returned_letter", service=sample_service)

    response = admin_request.delete(
        "service_callback.remove_returned_letter_callback_api",
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
    )

    assert response is None
    assert ServiceCallbackApi.query.count() == 0
