import json

from flask import url_for

from app.models import ApiKey
from tests import create_authorization_header


def test_api_key_should_create_new_api_key_for_service(notify_api, notify_db,
                                                       notify_db_session,
                                                       sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {'name': 'some secret name'}
            auth_header = create_authorization_header(path=url_for('service.renew_api_key',
                                                                   service_id=sample_service.id),
                                                      method='POST',
                                                      request_body=json.dumps(data))
            response = client.post(url_for('service.renew_api_key', service_id=sample_service.id),
                                   data=json.dumps(data),
                                   headers=[('Content-Type', 'application/json'), auth_header])
            assert response.status_code == 201
            assert response.get_data is not None
            saved_api_key = ApiKey.query.filter_by(service_id=sample_service.id).first()
            assert saved_api_key.service_id == sample_service.id
            assert saved_api_key.name == 'some secret name'


def test_api_key_should_return_error_when_service_does_not_exist(notify_api, notify_db, notify_db_session,
                                                                 sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(path=url_for('service.renew_api_key', service_id="123"),
                                                      method='POST')
            response = client.post(url_for('service.renew_api_key', service_id=123),
                                   headers=[('Content-Type', 'application/json'), auth_header])
            assert response.status_code == 404


def test_revoke_should_expire_api_key_for_service(notify_api, notify_db, notify_db_session,
                                                  sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert ApiKey.query.count() == 1
            auth_header = create_authorization_header(path=url_for('service.revoke_api_key',
                                                                   service_id=sample_api_key.service_id),
                                                      method='POST')
            response = client.post(url_for('service.revoke_api_key', service_id=sample_api_key.service_id),
                                   headers=[auth_header])
            assert response.status_code == 202
            api_keys_for_service = ApiKey.query.filter_by(service_id=sample_api_key.service_id).first()
            assert api_keys_for_service.expiry_date is not None


def test_api_key_should_create_multiple_new_api_key_for_service(notify_api, notify_db,
                                                                notify_db_session,
                                                                sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert ApiKey.query.count() == 0
            data = {'name': 'some secret name'}
            auth_header = create_authorization_header(path=url_for('service.renew_api_key',
                                                                   service_id=sample_service.id),
                                                      method='POST',
                                                      request_body=json.dumps(data))
            response = client.post(url_for('service.renew_api_key', service_id=sample_service.id),
                                   data=json.dumps(data),
                                   headers=[('Content-Type', 'application/json'), auth_header])
            assert response.status_code == 201
            assert ApiKey.query.count() == 1
            data = {'name': 'another secret name'}
            auth_header = create_authorization_header(path=url_for('service.renew_api_key',
                                                                   service_id=sample_service.id),
                                                      method='POST',
                                                      request_body=json.dumps(data))
            response2 = client.post(url_for('service.renew_api_key', service_id=sample_service.id),
                                    data=json.dumps(data),
                                    headers=[('Content-Type', 'application/json'), auth_header])
            assert response2.status_code == 201
            assert response2.get_data != response.get_data
            assert ApiKey.query.count() == 2
