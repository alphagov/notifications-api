import datetime
import pytest
from flask import json, url_for

from app import DATETIME_FORMAT
from tests import create_authorization_header
from tests.app.db import create_inbound_sms


def test_get_all_inbound_sms_returns_200(
        client, sample_service
):
    all_inbound_sms = [
        create_inbound_sms(service=sample_service, user_number='447700900111', content='Hi'),
        create_inbound_sms(service=sample_service, user_number='447700900112'),
        create_inbound_sms(service=sample_service, user_number='447700900111', content='Bye'),
        create_inbound_sms(service=sample_service, user_number='447700900113')
    ]

    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/inbound_sms',
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))['inbound_sms_list']

    reversed_all_inbound_sms = sorted(all_inbound_sms, key=lambda sms: sms.created_at, reverse=True)

    expected_response = [i.serialize() for i in reversed_all_inbound_sms]

    assert json_response == expected_response


def test_get_all_inbound_sms_for_no_inbound_sms_returns_200(
        client, sample_service
):
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/inbound_sms',
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))['inbound_sms_list']

    expected_response = []

    assert json_response == expected_response


def test_get_inbound_sms_by_number_returns_200(
        client, sample_service
):
    sample_inbound_sms = create_inbound_sms(service=sample_service)
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/inbound_sms/{}'.format(sample_inbound_sms.user_number),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))['inbound_sms_list']

    expected_response = [sample_inbound_sms.serialize()]

    assert json_response == expected_response


def test_get_inbound_sms_for_no_inbound_sms_returns_200(
        client, sample_service
):
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/inbound_sms',
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))['inbound_sms_list']

    expected_response = []

    assert json_response == expected_response


def test_get_inbound_sms_by_nonexistent_number(client, sample_service):
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/inbound_sms/447700900000',
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))['inbound_sms_list']
    expected_response = []

    assert json_response == expected_response


@pytest.mark.parametrize('invalid_number,expected_message', [
    ('0077700', 'Not enough digits'),
    ('123456789012', 'Not a UK mobile number'),
    ('invalid_number', 'Must not contain letters or symbols')
])
def test_get_inbound_sms_by_invalid_number(
        client, sample_service, invalid_number, expected_message):
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/inbound_sms/{}'.format(invalid_number),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))
    assert json_response == {
        "errors": [
            {
                "error": "BadRequestError",
                "message": expected_message
            }
        ],
        "status_code": 400
    }
