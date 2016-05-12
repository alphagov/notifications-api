from flask import json
from tests import create_authorization_header


def test_get_provider_details_in_type_and_identifier_order(notify_db, notify_db_session, notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            response = client.get(
                '/provider-details',
                headers=[auth_header]
            )
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))['provider_details']
            assert len(json_resp) == 3

            assert json_resp[0]['identifier'] == 'ses'
            assert json_resp[1]['identifier'] == 'mmg'
            assert json_resp[2]['identifier'] == 'firetext'


def test_get_provider_details_by_id(notify_db, notify_db_session, notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            response = client.get(
                '/provider-details',
                headers=[auth_header]
            )
            json_resp = json.loads(response.get_data(as_text=True))['provider_details']

            provider_resp = client.get(
                '/provider-details/{}'.format(json_resp[0]['id']),
                headers=[auth_header]
            )

            provider = json.loads(provider_resp.get_data(as_text=True))['provider_details']
            assert provider['identifier'] == json_resp[0]['identifier']


def test_get_provider_details_contains_correct_fields(notify_db, notify_db_session, notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            response = client.get(
                '/provider-details',
                headers=[auth_header]
            )
            json_resp = json.loads(response.get_data(as_text=True))['provider_details']
            allowed_keys = {"id", "display_name", "identifier", "priority", 'notification_type', "active"}
            assert \
                allowed_keys == \
                set(json_resp[0].keys())


def test_should_be_able_to_update_priority(notify_db, notify_db_session, notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            response = client.get(
                '/provider-details',
                headers=[auth_header]
            )
            fetch_resp = json.loads(response.get_data(as_text=True))['provider_details']

            provider_id = fetch_resp[2]['id']

            update_resp = client.post(
                '/provider-details/{}'.format(provider_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps({
                    'priority': 10
                })
            )
            assert update_resp.status_code == 200
            update_json = json.loads(update_resp.get_data(as_text=True))['provider_details']
            assert update_json['identifier'] == 'firetext'
            assert update_json['priority'] == 10


def test_should_be_able_to_update_status(notify_db, notify_db_session, notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            response = client.get(
                '/provider-details',
                headers=[auth_header]
            )
            fetch_resp = json.loads(response.get_data(as_text=True))['provider_details']

            provider_id = fetch_resp[2]['id']

            update_resp_1 = client.post(
                '/provider-details/{}'.format(provider_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps({
                    'active': False
                })
            )
            assert update_resp_1.status_code == 200
            update_resp_1 = json.loads(update_resp_1.get_data(as_text=True))['provider_details']
            assert update_resp_1['identifier'] == 'firetext'
            assert not update_resp_1['active']

            update_resp_2 = client.post(
                '/provider-details/{}'.format(provider_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps({
                    'active': True
                })
            )
            assert update_resp_2.status_code == 200
            update_resp_2 = json.loads(update_resp_2.get_data(as_text=True))['provider_details']
            assert update_resp_2['identifier'] == 'firetext'
            assert update_resp_2['active']


def test_should_not_be_able_to_update_identifier(notify_db, notify_db_session, notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            response = client.get(
                '/provider-details',
                headers=[auth_header]
            )
            fetch_resp = json.loads(response.get_data(as_text=True))['provider_details']

            provider_id = fetch_resp[2]['id']

            update_resp = client.post(
                '/provider-details/{}'.format(provider_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps({
                    'identifier': "new"
                })
            )
            assert update_resp.status_code == 400
            update_resp = json.loads(update_resp.get_data(as_text=True))
            assert update_resp['message']['identifier'][0] == 'Not permitted to be updated'
            assert update_resp['result'] == 'error'
