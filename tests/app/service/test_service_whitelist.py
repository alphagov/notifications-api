import uuid
import json

from tests import create_authorization_header

from app.models import ServiceWhitelist
from app.dao.service_whitelist_dao import dao_add_and_commit_whitelisted_contacts


def test_get_whitelist_returns_data(client, sample_service_whitelist):
    service_id = sample_service_whitelist.service_id

    response = client.get('service/{}/whitelist'.format(service_id), headers=[create_authorization_header()])

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {
        'email_addresses': [sample_service_whitelist.email_address],
        'mobile_numbers': []
    }


def test_get_whitelist_separates_emails_and_phones(client, sample_service):
    dao_add_and_commit_whitelisted_contacts([
        ServiceWhitelist.from_string(sample_service.id, 'service@example.com'),
        ServiceWhitelist.from_string(sample_service.id, '07123456789')
    ])

    response = client.get('service/{}/whitelist'.format(sample_service.id), headers=[create_authorization_header()])

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {
        'email_addresses': ['service@example.com'],
        'mobile_numbers': ['07123456789']
    }


def test_get_whitelist_404s_with_unknown_service_id(client):
    path = 'service/{}/api-keys'.format(uuid.uuid4())

    response = client.get(path, headers=[create_authorization_header()])

    assert response.status_code == 404
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'No result found'


def test_get_whitelist_returns_no_data(client, sample_service):
    path = 'service/{}/whitelist'.format(sample_service.id)

    response = client.get(path, headers=[create_authorization_header()])

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {'email_addresses': [], 'mobile_numbers': []}


def test_update_whitelist_replaces_old_whitelist(client, sample_service_whitelist):
    data = ['foo@bar.com', '07123456789']

    response = client.put(
        'service/{}/whitelist'.format(sample_service_whitelist.service_id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), create_authorization_header()]
    )

    assert response.status_code == 204
    whitelist = ServiceWhitelist.query.order_by(ServiceWhitelist.email_address).all()
    assert len(whitelist) == 2
    assert whitelist[0].email_address == 'foo@bar.com'
    assert whitelist[1].mobile_number == '07123456789'


def test_update_whitelist_doesnt_remove_old_whitelist_if_error(client, sample_service_whitelist):
    data = ['']
    response = client.put(
        'service/{}/whitelist'.format(sample_service_whitelist.service_id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), create_authorization_header()]
    )

    assert response.status_code == 400
    assert json.loads(response.get_data(as_text=True)) == {
        'result': 'error',
        'message': 'Invalid whitelist: "" is not a valid email address or phone number'
    }
    whitelist = ServiceWhitelist.query.one()
    assert whitelist.id == sample_service_whitelist.id
