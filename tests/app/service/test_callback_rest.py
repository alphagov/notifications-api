import json
import uuid

from tests import create_authorization_header

from tests.app.db import (
    create_service_inbound_api,
    create_service_callback_api
)


def test_create_service_inbound_api(client, sample_service):
    data = {
        "url": "https://some_service/inbound-sms",
        "bearer_token": "some-unique-string",
        "updated_by_id": str(sample_service.users[0].id)
    }
    response = client.post(
        '/service/{}/inbound-api'.format(sample_service.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), create_authorization_header()]
    )
    assert response.status_code == 201

    resp_json = json.loads(response.get_data(as_text=True))["data"]
    assert resp_json["id"]
    assert resp_json["service_id"] == str(sample_service.id)
    assert resp_json["url"] == "https://some_service/inbound-sms"
    assert resp_json["updated_by_id"] == str(sample_service.users[0].id)
    assert resp_json["created_at"]
    assert not resp_json["updated_at"]


def test_set_service_inbound_api_raises_404_when_service_does_not_exist(client):
    data = {
        "url": "https://some_service/inbound-sms",
        "bearer_token": "some-unique-string",
        "updated_by_id": str(uuid.uuid4())
    }
    response = client.post(
        '/service/{}/inbound-api'.format(uuid.uuid4()),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), create_authorization_header()]
    )
    assert response.status_code == 404
    assert json.loads(response.get_data(as_text=True))['message'] == 'No result found'


def test_update_service_inbound_api_updates_url(client, sample_service):
    service_inbound_api = create_service_inbound_api(service=sample_service,
                                                     url="https://original_url.com")

    data = {
        "url": "https://another_url.com",
        "updated_by_id": str(sample_service.users[0].id)
    }
    response = client.post("/service/{}/inbound-api/{}".format(sample_service.id, service_inbound_api.id),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))["data"]
    assert resp_json["url"] == "https://another_url.com"
    assert service_inbound_api.url == "https://another_url.com"


def test_update_service_inbound_api_updates_bearer_token(client, sample_service):
    service_inbound_api = create_service_inbound_api(service=sample_service,
                                                     bearer_token="some_super_secret")
    data = {
        "bearer_token": "different_token",
        "updated_by_id": str(sample_service.users[0].id)
    }
    response = client.post("/service/{}/inbound-api/{}".format(sample_service.id, service_inbound_api.id),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])
    assert response.status_code == 200
    assert service_inbound_api.bearer_token == "different_token"


def test_fetch_service_inbound_api(client, sample_service):
    service_inbound_api = create_service_inbound_api(service=sample_service)

    response = client.get("/service/{}/inbound-api/{}".format(sample_service.id, service_inbound_api.id),
                          headers=[create_authorization_header()])

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True))["data"] == service_inbound_api.serialize()


def test_create_service_callback_api(client, sample_service):
    data = {
        "url": "https://some_service/callback-endpoint",
        "bearer_token": "some-unique-string",
        "updated_by_id": str(sample_service.users[0].id)
    }
    response = client.post(
        '/service/{}/service-callback-api'.format(sample_service.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), create_authorization_header()]
    )
    assert response.status_code == 201

    resp_json = json.loads(response.get_data(as_text=True))["data"]
    assert resp_json["id"]
    assert resp_json["service_id"] == str(sample_service.id)
    assert resp_json["url"] == "https://some_service/callback-endpoint"
    assert resp_json["updated_by_id"] == str(sample_service.users[0].id)
    assert resp_json["created_at"]
    assert not resp_json["updated_at"]


def test_set_service_callback_api_raises_404_when_service_does_not_exist(client, notify_db_session):
    data = {
        "url": "https://some_service/service-callback-endpoint",
        "bearer_token": "some-unique-string",
        "updated_by_id": str(uuid.uuid4())
    }
    response = client.post(
        '/service/{}/service-callback-api'.format(uuid.uuid4()),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), create_authorization_header()]
    )
    assert response.status_code == 404
    assert json.loads(response.get_data(as_text=True))['message'] == 'No result found'


def test_update_service_callback_api_updates_url(client, sample_service):
    service_callback_api = create_service_callback_api(service=sample_service,
                                                       url="https://original_url.com")

    data = {
        "url": "https://another_url.com",
        "updated_by_id": str(sample_service.users[0].id)
    }
    response = client.post("/service/{}/service-callback-api/{}".format(sample_service.id, service_callback_api.id),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))["data"]
    assert resp_json["url"] == "https://another_url.com"
    assert service_callback_api.url == "https://another_url.com"


def test_update_service_callback_api_updates_bearer_token(client, sample_service):
    service_callback_api = create_service_callback_api(service=sample_service,
                                                       bearer_token="some_super_secret")
    data = {
        "bearer_token": "different_token",
        "updated_by_id": str(sample_service.users[0].id)
    }
    response = client.post("/service/{}/service-callback-api/{}".format(sample_service.id, service_callback_api.id),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])
    assert response.status_code == 200
    assert service_callback_api.bearer_token == "different_token"


def test_fetch_service_callback_api(client, sample_service):
    service_callback_api = create_service_callback_api(service=sample_service)

    response = client.get("/service/{}/service-callback-api/{}".format(sample_service.id, service_callback_api.id),
                          headers=[create_authorization_header()])

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True))["data"] == service_callback_api.serialize()
