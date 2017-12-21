from flask import json, url_for

from tests import create_authorization_header
from tests.app.db import create_inbound_sms


def test_get_inbound_sms_returns_200(
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


def test_get_inbound_sms_generate_page_links(client, sample_service, mocker):
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
        url_for('v2_inbound_sms.get_inbound_sms'),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200

    json_response = json.loads(response.get_data(as_text=True))
    expected_inbound_sms_list = [i.serialize() for i in reversed_inbound_sms[:2]]

    assert json_response['received_text_messages'] == expected_inbound_sms_list
    assert url_for(
        'v2_inbound_sms.get_inbound_sms',
        _external=True) == json_response['links']['current']
    assert url_for(
        'v2_inbound_sms.get_inbound_sms',
        older_than=reversed_inbound_sms[1].id,
        _external=True) == json_response['links']['next']


def test_get_next_inbound_sms_will_get_correct_inbound_sms_list(client, sample_service, mocker):
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
        path=url_for('v2_inbound_sms.get_inbound_sms', older_than=reversed_inbound_sms[1].id),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200

    json_response = json.loads(response.get_data(as_text=True))
    expected_inbound_sms_list = [i.serialize() for i in reversed_inbound_sms[2:]]

    assert json_response['received_text_messages'] == expected_inbound_sms_list
    assert url_for(
        'v2_inbound_sms.get_inbound_sms',
        _external=True) == json_response['links']['current']
    assert url_for(
        'v2_inbound_sms.get_inbound_sms',
        older_than=reversed_inbound_sms[3].id,
        _external=True) == json_response['links']['next']


def test_get_next_inbound_sms_at_end_will_return_empty_inbound_sms_list(client, sample_service, mocker):
    inbound_sms = create_inbound_sms(service=sample_service)
    mocker.patch.dict(
        "app.v2.inbound_sms.get_inbound_sms.current_app.config",
        {"API_PAGE_SIZE": 1}
    )

    auth_header = create_authorization_header(service_id=inbound_sms.service.id)
    response = client.get(
        path=url_for('v2_inbound_sms.get_inbound_sms', older_than=inbound_sms.id),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200

    json_response = json.loads(response.get_data(as_text=True))
    expected_inbound_sms_list = []
    assert json_response['received_text_messages'] == expected_inbound_sms_list
    assert url_for(
        'v2_inbound_sms.get_inbound_sms',
        _external=True) == json_response['links']['current']
    assert 'next' not in json_response['links'].keys()


def test_get_inbound_sms_for_no_inbound_sms_returns_empty_list(
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
        path='/v2/received-text-messages?user_number=447700900000',
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert json_response['status_code'] == 400
    assert json_response['errors'][0]['error'] == 'ValidationError'
    assert json_response['errors'][0]['message'] == \
        'Additional properties are not allowed (user_number was unexpected)'
