import json
import uuid

from app.models import ServiceDataRetention
from tests import create_authorization_header
from tests.app.db import create_service_data_retention


def test_get_service_data_retention(client, sample_service):
    sms_data_retention = create_service_data_retention(service_id=sample_service.id)
    email_data_retention = create_service_data_retention(service_id=sample_service.id, notification_type='email',
                                                         days_of_retention=10)
    letter_data_retention = create_service_data_retention(service_id=sample_service.id, notification_type='letter',
                                                          days_of_retention=30)

    response = client.get(
        '/service/{}/data-retention'.format(str(sample_service.id)),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
    )

    assert response.status_code == 200
    json_response = json.loads(response.get_data(as_text=True))
    assert len(json_response) == 3
    assert json_response[0] == email_data_retention.serialize()
    assert json_response[1] == sms_data_retention.serialize()
    assert json_response[2] == letter_data_retention.serialize()


def test_get_service_data_retention_returns_empty_list(client, sample_service):
    response = client.get(
        '/service/{}/data-retention'.format(str(sample_service.id)),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
    )
    assert response.status_code == 200
    assert len(json.loads(response.get_data(as_text=True))) == 0


def test_get_data_retention_for_service_notification_type(client, sample_service):
    data_retention = create_service_data_retention(service_id=sample_service.id)
    response = client.get('/service/{}/data-retention/notification-type/{}'.format(sample_service.id, 'sms'),
                          headers=[('Content-Type', 'application/json'), create_authorization_header()],
                          )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == data_retention.serialize()


def test_get_service_data_retention_by_id(client, sample_service):
    sms_data_retention = create_service_data_retention(service_id=sample_service.id)
    create_service_data_retention(service_id=sample_service.id, notification_type='email',
                                  days_of_retention=10)
    create_service_data_retention(service_id=sample_service.id, notification_type='letter',
                                  days_of_retention=30)
    response = client.get(
        '/service/{}/data-retention/{}'.format(str(sample_service.id), sms_data_retention.id),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
    )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == sms_data_retention.serialize()


def test_get_service_data_retention_by_id_returns_none_when_no_data_retention_exists(client, sample_service):
    response = client.get(
        '/service/{}/data-retention/{}'.format(str(sample_service.id), uuid.uuid4()),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
    )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {}


def test_create_service_data_retention(client, sample_service):
    data = {
        "notification_type": 'sms',
        "days_of_retention": 3
    }
    response = client.post(
        '/service/{}/data-retention'.format(str(sample_service.id)),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=json.dumps(data)
    )

    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))['result']
    results = ServiceDataRetention.query.all()
    assert len(results) == 1
    data_retention = results[0]
    assert json_resp == data_retention.serialize()


def test_create_service_data_retention_returns_400_when_notification_type_is_invalid(client):
    data = {
        "notification_type": 'unknown',
        "days_of_retention": 3
    }
    response = client.post(
        '/service/{}/data-retention'.format(str(uuid.uuid4())),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=json.dumps(data)
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['errors'][0]['error'] == 'ValidationError'
    assert json_resp['errors'][0]['message'] == 'notification_type unknown is not one of [sms, letter, email]'


def test_create_service_data_retention_returns_400_when_data_retention_for_notification_type_already_exists(
        client, sample_service
):
    create_service_data_retention(service_id=sample_service.id)
    data = {
        "notification_type": "sms",
        "days_of_retention": 3
    }
    response = client.post(
        '/service/{}/data-retention'.format(str(uuid.uuid4())),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=json.dumps(data)
    )

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'Service already has data retention for sms notification type'


def test_modify_service_data_retention(client, sample_service):
    data_retention = create_service_data_retention(service_id=sample_service.id)
    data = {
        "days_of_retention": 3
    }
    response = client.post(
        '/service/{}/data-retention/{}'.format(sample_service.id, data_retention.id),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=json.dumps(data)
    )
    assert response.status_code == 204
    assert response.get_data(as_text=True) == ''


def test_modify_service_data_retention_returns_400_when_data_retention_does_not_exist(client, sample_service):
    data = {
        "days_of_retention": 3
    }
    response = client.post(
        '/service/{}/data-retention/{}'.format(sample_service.id, uuid.uuid4()),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=json.dumps(data)
    )

    assert response.status_code == 404


def test_modify_service_data_retention_returns_400_when_data_is_invalid(client):
    data = {
        "bad_key": 3
    }
    response = client.post(
        '/service/{}/data-retention/{}'.format(uuid.uuid4(), uuid.uuid4()),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=json.dumps(data)
    )
    assert response.status_code == 400
