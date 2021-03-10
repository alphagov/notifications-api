import uuid

from app.models import ServiceCallbackApi, ServiceInboundApi
from tests.app.db import create_service_callback_api, create_service_inbound_api


def test_create_service_inbound_api(admin_request, sample_service):
    data = {
        "url": "https://some_service/inbound-sms",
        "bearer_token": "some-unique-string",
        "updated_by_id": str(sample_service.users[0].id)
    }
    resp_json = admin_request.post(
        'service_callback.create_service_inbound_api',
        service_id=sample_service.id,
        _data=data,
        _expected_status=201
    )

    resp_json = resp_json["data"]
    assert resp_json["id"]
    assert resp_json["service_id"] == str(sample_service.id)
    assert resp_json["url"] == "https://some_service/inbound-sms"
    assert resp_json["updated_by_id"] == str(sample_service.users[0].id)
    assert resp_json["created_at"]
    assert not resp_json["updated_at"]


def test_set_service_inbound_api_raises_404_when_service_does_not_exist(admin_request):
    data = {
        "url": "https://some_service/inbound-sms",
        "bearer_token": "some-unique-string",
        "updated_by_id": str(uuid.uuid4())
    }
    response = admin_request.post(
        'service_callback.create_service_inbound_api',
        service_id=uuid.uuid4(),
        _data=data,
        _expected_status=404
    )
    assert response['message'] == 'No result found'


def test_update_service_inbound_api_updates_url(admin_request, sample_service):
    service_inbound_api = create_service_inbound_api(service=sample_service,
                                                     url="https://original_url.com")

    data = {
        "url": "https://another_url.com",
        "updated_by_id": str(sample_service.users[0].id)
    }

    response = admin_request.post(
        'service_callback.update_service_inbound_api',
        service_id=sample_service.id,
        inbound_api_id=service_inbound_api.id,
        _data=data
    )

    assert response["data"]["url"] == "https://another_url.com"
    assert service_inbound_api.url == "https://another_url.com"


def test_update_service_inbound_api_updates_bearer_token(admin_request, sample_service):
    service_inbound_api = create_service_inbound_api(service=sample_service,
                                                     bearer_token="some_super_secret")
    data = {
        "bearer_token": "different_token",
        "updated_by_id": str(sample_service.users[0].id)
    }

    admin_request.post(
        'service_callback.update_service_inbound_api',
        service_id=sample_service.id,
        inbound_api_id=service_inbound_api.id,
        _data=data
    )
    assert service_inbound_api.bearer_token == "different_token"


def test_fetch_service_inbound_api(admin_request, sample_service):
    service_inbound_api = create_service_inbound_api(service=sample_service)

    response = admin_request.get(
        'service_callback.fetch_service_inbound_api',
        service_id=sample_service.id,
        inbound_api_id=service_inbound_api.id,
    )
    assert response["data"] == service_inbound_api.serialize()


def test_delete_service_inbound_api(admin_request, sample_service):
    service_inbound_api = create_service_inbound_api(sample_service)

    response = admin_request.delete(
        'service_callback.remove_service_inbound_api',
        service_id=sample_service.id,
        inbound_api_id=service_inbound_api.id,
    )

    assert response is None
    assert ServiceInboundApi.query.count() == 0


def test_create_service_callback_api(admin_request, sample_service):
    data = {
        "url": "https://some_service/delivery-receipt-endpoint",
        "bearer_token": "some-unique-string",
        "updated_by_id": str(sample_service.users[0].id)
    }

    resp_json = admin_request.post(
        'service_callback.create_service_callback_api',
        service_id=sample_service.id,
        _data=data,
        _expected_status=201
    )

    resp_json = resp_json["data"]
    assert resp_json["id"]
    assert resp_json["service_id"] == str(sample_service.id)
    assert resp_json["url"] == "https://some_service/delivery-receipt-endpoint"
    assert resp_json["updated_by_id"] == str(sample_service.users[0].id)
    assert resp_json["created_at"]
    assert not resp_json["updated_at"]


def test_set_service_callback_api_raises_404_when_service_does_not_exist(admin_request, notify_db_session):
    data = {
        "url": "https://some_service/delivery-receipt-endpoint",
        "bearer_token": "some-unique-string",
        "updated_by_id": str(uuid.uuid4())
    }

    resp_json = admin_request.post(
        'service_callback.create_service_callback_api',
        service_id=uuid.uuid4(),
        _data=data,
        _expected_status=404
    )
    assert resp_json['message'] == 'No result found'


def test_update_service_callback_api_updates_url(admin_request, sample_service):
    service_callback_api = create_service_callback_api(service=sample_service,
                                                       url="https://original_url.com")

    data = {
        "url": "https://another_url.com",
        "updated_by_id": str(sample_service.users[0].id)
    }

    resp_json = admin_request.post(
        'service_callback.update_service_callback_api',
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
        _data=data
    )
    assert resp_json["data"]["url"] == "https://another_url.com"
    assert service_callback_api.url == "https://another_url.com"


def test_update_service_callback_api_updates_bearer_token(admin_request, sample_service):
    service_callback_api = create_service_callback_api(service=sample_service,
                                                       bearer_token="some_super_secret")
    data = {
        "bearer_token": "different_token",
        "updated_by_id": str(sample_service.users[0].id)
    }

    admin_request.post(
        'service_callback.update_service_callback_api',
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
        _data=data
    )
    assert service_callback_api.bearer_token == "different_token"


def test_fetch_service_callback_api(admin_request, sample_service):
    service_callback_api = create_service_callback_api(service=sample_service)

    response = admin_request.get(
        'service_callback.fetch_service_callback_api',
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
    )

    assert response["data"] == service_callback_api.serialize()


def test_delete_service_callback_api(admin_request, sample_service):
    service_callback_api = create_service_callback_api(sample_service)

    response = admin_request.delete(
        'service_callback.remove_service_callback_api',
        service_id=sample_service.id,
        callback_api_id=service_callback_api.id,
    )

    assert response is None
    assert ServiceCallbackApi.query.count() == 0
