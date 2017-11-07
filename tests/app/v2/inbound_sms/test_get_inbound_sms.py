import pytest
from flask import json, url_for

from tests import create_authorization_header
from tests.app.db import create_inbound_sms


def test_get_all_inbound_sms_returns_200(
        client, sample_service
):
    all_inbound_sms = [
        create_inbound_sms(service=sample_service, user_number='447700900111', content='Hi'),
        create_inbound_sms(service=sample_service, user_number='447700900112'),
        create_inbound_sms(service=sample_service, user_number='447700900111', content='Bye'),
        create_inbound_sms(service=sample_service, user_number='07700900113')
    ]

    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/received-text-messages',
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))['received_text_messages']

    reversed_all_inbound_sms = sorted(all_inbound_sms, key=lambda sms: sms.created_at, reverse=True)

    expected_response = [i.serialize() for i in reversed_all_inbound_sms]

    assert json_response == expected_response


@pytest.mark.parametrize('user_number', [None, '447700900111'])
def test_get_inbound_sms_generate_page_links(
        client, sample_service, mocker, user_number
):
    mocker.patch.dict(
        "app.v2.inbound_sms.get_inbound_sms.current_app.config",
        {"API_PAGE_SIZE": 2}
    )
    all_inbound_sms = [
        create_inbound_sms(service=sample_service, user_number='447700900111', content='Hi'),
        create_inbound_sms(service=sample_service, user_number='447700900111'),
        create_inbound_sms(service=sample_service, user_number='447700900111', content='End'),
    ]

    reversed_inbound_sms = sorted(all_inbound_sms, key=lambda sms: sms.created_at, reverse=True)

    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        url_for('v2_inbound_sms.get_inbound_sms', user_number=user_number),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200

    json_response = json.loads(response.get_data(as_text=True))
    expected_inbound_sms_list = [i.serialize() for i in reversed_inbound_sms[:2]]

    assert json_response['received_text_messages'] == expected_inbound_sms_list
    assert url_for(
        'v2_inbound_sms.get_inbound_sms',
        user_number=user_number,
        _external=True) == json_response['links']['current']
    assert url_for(
        'v2_inbound_sms.get_inbound_sms',
        user_number=user_number,
        older_than=reversed_inbound_sms[1].id,
        _external=True) == json_response['links']['next']


@pytest.mark.parametrize('user_number', [None, '447700900111'])
def test_get_next_inbound_sms_will_get_correct_inbound_sms_list(
        client, sample_service, mocker, user_number
):
    mocker.patch.dict(
        "app.v2.inbound_sms.get_inbound_sms.current_app.config",
        {"API_PAGE_SIZE": 2}
    )
    all_inbound_sms = [
        create_inbound_sms(service=sample_service, user_number='447700900111', content='1'),
        create_inbound_sms(service=sample_service, user_number='447700900111', content='2'),
        create_inbound_sms(service=sample_service, user_number='447700900111', content='3'),
        create_inbound_sms(service=sample_service, user_number='447700900111', content='4'),
    ]
    reversed_inbound_sms = sorted(all_inbound_sms, key=lambda sms: sms.created_at, reverse=True)

    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path=url_for('v2_inbound_sms.get_inbound_sms', user_number=user_number, older_than=reversed_inbound_sms[1].id),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200

    json_response = json.loads(response.get_data(as_text=True))
    expected_inbound_sms_list = [i.serialize() for i in reversed_inbound_sms[2:]]

    assert json_response['received_text_messages'] == expected_inbound_sms_list
    assert url_for(
        'v2_inbound_sms.get_inbound_sms',
        user_number=user_number,
        _external=True) == json_response['links']['current']
    assert url_for(
        'v2_inbound_sms.get_inbound_sms',
        user_number=user_number,
        older_than=reversed_inbound_sms[3].id,
        _external=True) == json_response['links']['next']


@pytest.mark.parametrize('user_number', [None, '447700900111'])
def test_get_next_inbound_sms_at_end_will_return_empty_inbound_sms_list(
        client, sample_inbound_sms, mocker, user_number
):
    mocker.patch.dict(
        "app.v2.inbound_sms.get_inbound_sms.current_app.config",
        {"API_PAGE_SIZE": 1}
    )

    auth_header = create_authorization_header(service_id=sample_inbound_sms.service.id)
    response = client.get(
        path=url_for('v2_inbound_sms.get_inbound_sms', user_number=user_number, older_than=sample_inbound_sms.id),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200

    json_response = json.loads(response.get_data(as_text=True))
    expected_inbound_sms_list = []
    assert json_response['received_text_messages'] == expected_inbound_sms_list
    assert url_for(
        'v2_inbound_sms.get_inbound_sms',
        user_number=user_number,
        _external=True) == json_response['links']['current']
    assert 'next' not in json_response['links'].keys()


def test_get_all_inbound_sms_for_no_inbound_sms_returns_200(
        client, sample_service
):
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/received-text-messages',
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))['received_text_messages']

    expected_response = []

    assert json_response == expected_response


@pytest.mark.parametrize('requested_number', [
    '447700900111',
    '+447700900111',
    '07700900111'
])
def test_get_inbound_sms_by_number_returns_200(
        client, sample_service, requested_number
):
    sample_inbound_sms1 = create_inbound_sms(service=sample_service, user_number='447700900111')
    create_inbound_sms(service=sample_service, user_number='447700900112')
    sample_inbound_sms2 = create_inbound_sms(service=sample_service, user_number='447700900111')
    create_inbound_sms(service=sample_service, user_number='447700900113')

    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/received-text-messages?user_number={}'.format(requested_number),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))['received_text_messages']

    expected_response = [sample_inbound_sms2.serialize(), sample_inbound_sms1.serialize()]

    assert json_response == expected_response


def test_get_inbound_sms_for_no_inbound_sms_returns_200(
        client, sample_service
):
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/received-text-messages',
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))['received_text_messages']

    expected_response = []

    assert json_response == expected_response


def test_get_inbound_sms_with_invalid_query_string_returns_400(client, sample_service):
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/received-text-messages?usernumber=447700900000',
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert json_response['status_code'] == 400
    assert json_response['errors'][0]['error'] == 'ValidationError'
    assert json_response['errors'][0]['message'] == \
        'Additional properties are not allowed (usernumber was unexpected)'


def test_get_inbound_sms_by_nonexistent_number(client, sample_service):
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/received-text-messages?user_number=447700900000',
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))['received_text_messages']
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
        path='/v2/received-text-messages?user_number={}'.format(invalid_number),
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
