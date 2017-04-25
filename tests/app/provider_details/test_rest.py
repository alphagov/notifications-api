import pytest
from flask import json

from app.models import ProviderDetails, ProviderDetailsHistory

from tests import create_authorization_header


def test_get_provider_details_in_type_and_identifier_order(client, notify_db):
    response = client.get(
        '/provider-details',
        headers=[create_authorization_header()]
    )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))['provider_details']
    assert len(json_resp) == 5

    assert json_resp[0]['identifier'] == 'ses'
    assert json_resp[1]['identifier'] == 'mmg'
    assert json_resp[2]['identifier'] == 'firetext'
    assert json_resp[3]['identifier'] == 'loadtesting'
    assert json_resp[4]['identifier'] == 'dvla'


def test_get_provider_details_by_id(client, notify_db):
    response = client.get(
        '/provider-details',
        headers=[create_authorization_header()]
    )
    json_resp = json.loads(response.get_data(as_text=True))['provider_details']

    provider_resp = client.get(
        '/provider-details/{}'.format(json_resp[0]['id']),
        headers=[create_authorization_header()]
    )

    provider = json.loads(provider_resp.get_data(as_text=True))['provider_details']
    assert provider['identifier'] == json_resp[0]['identifier']


def test_get_provider_details_contains_correct_fields(client, notify_db):
    response = client.get(
        '/provider-details',
        headers=[create_authorization_header()]
    )
    json_resp = json.loads(response.get_data(as_text=True))['provider_details']
    allowed_keys = {
        "id", "created_by", "display_name",
        "identifier", "priority", 'notification_type',
        "active", "version", "updated_at", "supports_international"
    }
    assert allowed_keys == set(json_resp[0].keys())


def test_should_be_able_to_update_priority(client, restore_provider_details):
    provider = ProviderDetails.query.first()

    update_resp = client.post(
        '/provider-details/{}'.format(provider.id),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=json.dumps({
            'priority': 5
        })
    )
    assert update_resp.status_code == 200
    update_json = json.loads(update_resp.get_data(as_text=True))['provider_details']
    assert update_json['identifier'] == provider.identifier
    assert update_json['priority'] == 5
    assert provider.priority == 5


def test_should_be_able_to_update_status(client, restore_provider_details):
    provider = ProviderDetails.query.first()

    update_resp_1 = client.post(
        '/provider-details/{}'.format(provider.id),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=json.dumps({
            'active': False
        })
    )
    assert update_resp_1.status_code == 200
    update_resp_1 = json.loads(update_resp_1.get_data(as_text=True))['provider_details']
    assert update_resp_1['identifier'] == provider.identifier
    assert not update_resp_1['active']
    assert not provider.active


@pytest.mark.parametrize('field,value', [
    ('identifier', 'new'),
    ('version', 7),
    ('updated_at', None)
])
def test_should_not_be_able_to_update_disallowed_fields(client, restore_provider_details, field, value):
    provider = ProviderDetails.query.first()

    resp = client.post(
        '/provider-details/{}'.format(provider.id),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=json.dumps({field: value})
    )
    resp_json = json.loads(resp.get_data(as_text=True))

    assert resp_json['message'][field][0] == 'Not permitted to be updated'
    assert resp_json['result'] == 'error'
    assert resp.status_code == 400


def test_get_provider_versions_contains_correct_fields(client, notify_db):
    provider = ProviderDetailsHistory.query.first()
    response = client.get(
        '/provider-details/{}/versions'.format(provider.id),
        headers=[create_authorization_header()]
    )
    json_resp = json.loads(response.get_data(as_text=True))['data']
    allowed_keys = {
        "id", "created_by", "display_name",
        "identifier", "priority", 'notification_type',
        "active", "version", "updated_at", "supports_international"
    }
    assert allowed_keys == set(json_resp[0].keys())


def test_update_provider_should_store_user_id(client, restore_provider_details, sample_user):
    provider = ProviderDetails.query.first()

    update_resp_1 = client.post(
        '/provider-details/{}'.format(provider.id),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=json.dumps({
            'created_by': sample_user.id,
            'active': False
        })
    )
    assert update_resp_1.status_code == 200
    update_resp_1 = json.loads(update_resp_1.get_data(as_text=True))['provider_details']
    assert update_resp_1['identifier'] == provider.identifier
    assert not update_resp_1['active']
    assert not provider.active
