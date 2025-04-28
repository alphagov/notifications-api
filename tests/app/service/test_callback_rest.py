import uuid

import pytest

from app.constants import ServiceCallbackTypes
from app.models import ServiceCallbackApi, ServiceInboundApi
from tests.app.db import create_service_callback_api


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


def test_create_service_callback_api_writes_to_both_callback_tables_for_inbound_sms(admin_request, sample_service):
    data = {
        "url": "https://some_service/inbound-sms",
        "bearer_token": "some-unique-string",
        "updated_by_id": str(sample_service.users[0].id),
        "callback_type": ServiceCallbackTypes.inbound_sms.value,
    }

    admin_request.post(
        "service_callback.create_service_callback_api", service_id=sample_service.id, _data=data, _expected_status=201
    )

    service_inbound_api_object = ServiceInboundApi.query.one()
    service_callback_api_object = ServiceCallbackApi.query.one()

    assert service_inbound_api_object.url == service_callback_api_object.url
    assert service_inbound_api_object.bearer_token == service_callback_api_object.bearer_token
    assert service_callback_api_object.callback_type == ServiceCallbackTypes.inbound_sms.value


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


@pytest.mark.parametrize(
    "callback_type, path",
    [
        (ServiceCallbackTypes.inbound_sms.value, "inbound-sms"),
        (ServiceCallbackTypes.delivery_status.value, "delivery-status"),
        (ServiceCallbackTypes.returned_letter.value, "returned-letter"),
    ],
)
def test_fetch_service_callback_api(admin_request, sample_service, callback_type, path):
    service_callback_api = create_service_callback_api(
        service=sample_service, callback_type=callback_type, url=f"https://something.com/{path}"
    )

    response = admin_request.get(
        "service_callback.fetch_service_callback_api",
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
        callback_type=callback_type,
    )
    assert response["data"] == service_callback_api.serialize()


@pytest.mark.parametrize(
    "callback_type",
    [
        ServiceCallbackTypes.inbound_sms.value,
        ServiceCallbackTypes.delivery_status.value,
        ServiceCallbackTypes.returned_letter.value,
    ],
)
def test_delete_service_callback_api(admin_request, sample_service, callback_type):
    service_callback_api = create_service_callback_api(callback_type=callback_type, service=sample_service)
    response = admin_request.delete(
        "service_callback.remove_service_callback_api",
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
        callback_type=callback_type,
    )
    assert response is None
    assert ServiceCallbackApi.query.count() == 0


@pytest.mark.parametrize(
    "callback_type",
    [
        ServiceCallbackTypes.inbound_sms.value,
        ServiceCallbackTypes.delivery_status.value,
        ServiceCallbackTypes.returned_letter.value,
    ],
)
def test_delete_service_callback_api_invalid_callback_id(admin_request, sample_service, callback_type):
    admin_request.delete(
        "service_callback.remove_service_callback_api",
        service_id=sample_service.id,
        callback_api_id=uuid.uuid4(),
        callback_type=callback_type,
        _expected_status=404,
    )
