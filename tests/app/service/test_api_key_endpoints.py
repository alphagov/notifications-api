import json
from datetime import timedelta, datetime

from flask import url_for
from app.models import ApiKey
from app.dao.api_key_dao import save_model_api_key
from tests import create_authorization_header
from tests.app.conftest import sample_api_key as create_sample_api_key
from tests.app.conftest import sample_service as create_sample_service
from tests.app.conftest import sample_user as create_user


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
            import uuid
            missing_service_id = uuid.uuid4()
            auth_header = create_authorization_header(path=url_for('service.renew_api_key',
                                                                   service_id=missing_service_id),
                                                      method='POST')
            response = client.post(url_for('service.renew_api_key', service_id=missing_service_id),
                                   headers=[('Content-Type', 'application/json'), auth_header])
            assert response.status_code == 404


def test_revoke_should_expire_api_key_for_service(notify_api, notify_db, notify_db_session,
                                                  sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert ApiKey.query.count() == 1
            auth_header = create_authorization_header(path=url_for('service.revoke_api_key',
                                                                   service_id=sample_api_key.service_id,
                                                                   api_key_id=sample_api_key.id),
                                                      method='POST')
            response = client.post(url_for('service.revoke_api_key',
                                           service_id=sample_api_key.service_id,
                                           api_key_id=sample_api_key.id),
                                   headers=[auth_header])
            assert response.status_code == 202
            api_keys_for_service = ApiKey.query.get(sample_api_key.id)
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


def test_get_api_keys_should_return_all_keys_for_service(notify_api, notify_db,
                                                         notify_db_session,
                                                         sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            another_user = create_user(notify_db, notify_db_session, email='another@it.gov.uk')
            another_service = create_sample_service(notify_db, notify_db_session, service_name='another',
                                                    user=another_user)
            create_sample_api_key(notify_db, notify_db_session, service=another_service)
            api_key2 = ApiKey(**{'service_id': sample_api_key.service_id, 'name': 'second_api_key'})
            api_key3 = ApiKey(**{'service_id': sample_api_key.service_id, 'name': 'third_api_key',
                                 'expiry_date': datetime.utcnow() + timedelta(hours=-1)})
            save_model_api_key(api_key2)
            save_model_api_key(api_key3)
            assert ApiKey.query.count() == 4

            auth_header = create_authorization_header(path=url_for('service.get_api_keys',
                                                                   service_id=sample_api_key.service_id),
                                                      method='GET')
            response = client.get(url_for('service.get_api_keys',
                                          service_id=sample_api_key.service_id),
                                  headers=[('Content-Type', 'application/json'), auth_header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['apiKeys']) == 3


def test_get_api_keys_should_return_one_key_for_service(notify_api, notify_db,
                                                        notify_db_session,
                                                        sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(path=url_for('service.get_api_keys',
                                                                   service_id=sample_api_key.service_id,
                                                                   key_id=sample_api_key.id),
                                                      method='GET')
            response = client.get(url_for('service.get_api_keys',
                                          service_id=sample_api_key.service_id,
                                          key_id=sample_api_key.id),
                                  headers=[('Content-Type', 'application/json'), auth_header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['apiKeys']) == 1
