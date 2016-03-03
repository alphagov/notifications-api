import json
import uuid
from flask import url_for
from app.dao.users_dao import save_model_user
from app.dao.services_dao import dao_remove_user_from_service
from app.models import User
from tests import create_authorization_header


def test_get_service_list(notify_api, service_factory):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_factory.get('one')
            service_factory.get('two')
            service_factory.get('three')
            auth_header = create_authorization_header(
                path='/service',
                method='GET'
            )
            response = client.get(
                '/service',
                headers=[auth_header]
            )
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 3
            assert json_resp['data'][0]['name'] == 'one'
            assert json_resp['data'][1]['name'] == 'two'
            assert json_resp['data'][2]['name'] == 'three'


def test_get_service_list_by_user(notify_api, sample_user, service_factory):

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_factory.get('one', sample_user)
            service_factory.get('two', sample_user)
            service_factory.get('three', sample_user)

            auth_header = create_authorization_header(
                path='/service',
                method='GET'
            )
            response = client.get(
                '/service?user_id='.format(sample_user.id),
                headers=[auth_header]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert len(json_resp['data']) == 3
            assert json_resp['data'][0]['name'] == 'one'
            assert json_resp['data'][1]['name'] == 'two'
            assert json_resp['data'][2]['name'] == 'three'


def test_get_service_list_by_user_should_return_empty_list_if_no_services(notify_api, service_factory, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            new_user = User(
                name='Test User',
                email_address='new_user@digital.cabinet-office.gov.uk',
                password='password',
                mobile_number='+447700900986'
            )
            save_model_user(new_user)

            service_factory.get('one', sample_user)
            service_factory.get('two', sample_user)
            service_factory.get('three', sample_user)

            auth_header = create_authorization_header(
                path='/service',
                method='GET'
            )
            response = client.get(
                '/service?user_id={}'.format(new_user.id),
                headers=[auth_header]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert len(json_resp['data']) == 0


def test_get_service_list_should_return_empty_list_if_no_services(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                path='/service',
                method='GET'
            )
            response = client.get(
                '/service',
                headers=[auth_header]
            )
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 0


def test_get_service_by_id(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                path='/service/{}'.format(sample_service.id),
                method='GET'
            )
            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[auth_header]
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == sample_service.name
            assert json_resp['data']['id'] == str(sample_service.id)


def test_get_service_by_id_should_404_if_no_service(notify_api, notify_db):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_id = str(uuid.uuid4())
            auth_header = create_authorization_header(
                path='/service/{}'.format(service_id),
                method='GET'
            )
            resp = client.get(
                '/service/{}'.format(service_id),
                headers=[auth_header]
            )
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Service not found for service id: {} '.format(service_id)


def test_get_service_by_id_and_user(notify_api, service_factory, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service = service_factory.get('new service', sample_user)
            auth_header = create_authorization_header(
                path='/service/{}'.format(service.id),
                method='GET'
            )
            resp = client.get(
                '/service/{}?user_id={}'.format(service.id, sample_user.id),
                headers=[auth_header]
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == service.name
            assert json_resp['data']['id'] == str(service.id)


def test_get_service_by_id_should_404_if_no_service_for_user(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_id = str(uuid.uuid4())
            auth_header = create_authorization_header(
                path='/service/{}'.format(service_id),
                method='GET'
            )
            resp = client.get(
                '/service/{}?user_id={}'.format(service_id, sample_user.id),
                headers=[auth_header]
            )
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == \
                'Service not found for service id: {0} and for user id: {1}'.format(service_id, sample_user.id)


def test_create_service(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'created service',
                'user_id': sample_user.id,
                'limit': 1000,
                'restricted': False,
                'active': False}
            auth_header = create_authorization_header(
                path='/service',
                method='POST',
                request_body=json.dumps(data)
            )
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 201
            assert json_resp['data']['id']
            assert json_resp['data']['name'] == 'created service'
            assert json_resp['data']['email_from'] == 'created.service'

            auth_header_fetch = create_authorization_header(
                path='/service/{}'.format(json_resp['data']['id']),
                method='GET'
            )

            resp = client.get(
                '/service/{}?user_id={}'.format(json_resp['data']['id'], sample_user.id),
                headers=[auth_header_fetch]
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == 'created service'


def test_should_not_create_service_with_missing_user_id_field(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'email_from': 'service',
                'name': 'created service',
                'limit': 1000,
                'restricted': False,
                'active': False
            }
            auth_header = create_authorization_header(
                path='/service',
                method='POST',
                request_body=json.dumps(data)
            )
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['user_id']


def test_should_not_create_service_with_missing_if_user_id_is_not_in_database(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'email_from': 'service',
                'user_id': 1234,
                'name': 'created service',
                'limit': 1000,
                'restricted': False,
                'active': False
            }
            auth_header = create_authorization_header(
                path='/service',
                method='POST',
                request_body=json.dumps(data)
            )
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'not found' in json_resp['message']['user_id']


def test_should_not_create_service_if_missing_data(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'user_id': sample_user.id
            }
            auth_header = create_authorization_header(
                path='/service',
                method='POST',
                request_body=json.dumps(data)
            )
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['name']
            assert 'Missing data for required field.' in json_resp['message']['active']
            assert 'Missing data for required field.' in json_resp['message']['limit']
            assert 'Missing data for required field.' in json_resp['message']['restricted']


def test_update_service(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                path='/service/{}'.format(sample_service.id),
                method='GET'
            )
            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[auth_header]
            )
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert json_resp['data']['name'] == sample_service.name

            data = {
                'name': 'updated service name'
            }

            auth_header = create_authorization_header(
                path='/service/{}'.format(sample_service.id),
                method='POST',
                request_body=json.dumps(data)
            )

            resp = client.post(
                '/service/{}'.format(sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            result = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert result['data']['name'] == 'updated service name'


def test_update_service_should_404_if_id_is_invalid(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'updated service name'
            }

            missing_service_id = uuid.uuid4()

            auth_header = create_authorization_header(
                path='/service/{}'.format(missing_service_id),
                method='POST',
                request_body=json.dumps(data)
            )

            resp = client.post(
                '/service/{}'.format(missing_service_id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert resp.status_code == 404


def test_get_users_by_service(notify_api, notify_db, notify_db_session, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user_on_service = sample_service.users[0]
            auth_header = create_authorization_header(
                path='/service/{}/users'.format(sample_service.id),
                method='GET'
            )

            resp = client.get(
                '/service/{}/users'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header]
            )

            assert resp.status_code == 200
            result = json.loads(resp.get_data(as_text=True))
            assert len(result['data']) == 1
            assert result['data'][0]['name'] == user_on_service.name
            assert result['data'][0]['email_address'] == user_on_service.email_address
            assert result['data'][0]['mobile_number'] == user_on_service.mobile_number


def test_get_users_for_service_returns_empty_list_if_no_users_associated_with_service(notify_api,
                                                                                      notify_db,
                                                                                      notify_db_session,
                                                                                      sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            dao_remove_user_from_service(sample_service, sample_service.users[0])
            auth_header = create_authorization_header(
                path='/service/{}/users'.format(sample_service.id),
                method='GET'
            )

            response = client.get(
                '/service/{}/users'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            result = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert result['data'] == []


def test_get_users_for_service_returns_404_when_service_does_not_exist(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_id = uuid.uuid4()
            auth_header = create_authorization_header(
                path='/service/{}/users'.format(service_id),
                method='GET'
            )

            response = client.get(
                '/service/{}/users'.format(service_id),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert response.status_code == 404
            result = json.loads(response.get_data(as_text=True))
            assert result['result'] == 'error'
            assert result['message'] == 'Service not found for id: {}'.format(service_id)


def test_default_permissions_are_added_for_user_service(notify_api,
                                                        notify_db,
                                                        notify_db_session,
                                                        sample_service,
                                                        sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'created service',
                'user_id': sample_user.id,
                'limit': 1000,
                'restricted': False,
                'active': False}
            auth_header = create_authorization_header(
                path='/service',
                method='POST',
                request_body=json.dumps(data)
            )
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 201
            assert json_resp['data']['id']
            assert json_resp['data']['name'] == 'created service'
            assert json_resp['data']['email_from'] == 'created.service'

            auth_header_fetch = create_authorization_header(
                path='/service/{}'.format(json_resp['data']['id']),
                method='GET'
            )

            resp = client.get(
                '/service/{}?user_id={}'.format(json_resp['data']['id'], sample_user.id),
                headers=[auth_header_fetch]
            )
            assert resp.status_code == 200
            header = create_authorization_header(
                path=url_for('user.get_user', user_id=sample_user.id),
                method='GET')
            response = client.get(
                url_for('user.get_user', user_id=sample_user.id),
                headers=[header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            service_permissions = json_resp['data']['permissions'][str(sample_service.id)]
            from app.dao.permissions_dao import default_service_permissions
            assert sorted(default_service_permissions) == sorted(service_permissions)


def test_add_existing_user_to_another_service_with_all_permissions(notify_api,
                                                                   notify_db,
                                                                   notify_db_session,
                                                                   sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            # check which users part of service
            user_already_in_service = sample_service.users[0]
            auth_header = create_authorization_header(
                path='/service/{}/users'.format(sample_service.id),
                method='GET'
            )

            resp = client.get(
                '/service/{}/users'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header]
            )

            assert resp.status_code == 200
            result = json.loads(resp.get_data(as_text=True))
            assert len(result['data']) == 1
            assert result['data'][0]['email_address'] == user_already_in_service.email_address

            # add new user to service
            user_to_add = User(
                name='Invited User',
                email_address='invited@digital.cabinet-office.gov.uk',
                password='password',
                mobile_number='+4477123456'
            )
            # they must exist in db first
            save_model_user(user_to_add)

            data = {'permissions': ['send_messages', 'manage_service', 'manage_api_keys']}
            auth_header = create_authorization_header(
                path='/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                request_body=json.dumps(data),
                method='POST'
            )

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            assert resp.status_code == 201

            # check new user added to service
            auth_header = create_authorization_header(
                path='/service/{}'.format(sample_service.id),
                method='GET'
            )

            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header],
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert user_to_add.id in json_resp['data']['users']

            # check user has all permissions
            auth_header = create_authorization_header(
                path=url_for('user.get_user', user_id=user_to_add.id),
                method='GET'
            )
            resp = client.get(url_for('user.get_user', user_id=user_to_add.id),
                              headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            permissions = json_resp['data']['permissions'][str(sample_service.id)]
            expected_permissions = ['send_texts', 'send_emails', 'send_letters', 'manage_users',
                                    'manage_settings', 'manage_templates', 'manage_api_keys',
                                    'access_developer_docs']
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_another_service_with_send_permissions(notify_api,
                                                                    notify_db,
                                                                    notify_db_session,
                                                                    sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            # they must exist in db first
            user_to_add = User(
                name='Invited User',
                email_address='invited@digital.cabinet-office.gov.uk',
                password='password',
                mobile_number='+4477123456'
            )
            save_model_user(user_to_add)

            data = {'permissions': ['send_messages']}
            auth_header = create_authorization_header(
                path='/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                request_body=json.dumps(data),
                method='POST'
            )

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_authorization_header(
                path=url_for('user.get_user', user_id=user_to_add.id),
                method='GET'
            )
            resp = client.get(url_for('user.get_user', user_id=user_to_add.id),
                              headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))

            permissions = json_resp['data']['permissions'][str(sample_service.id)]
            expected_permissions = ['send_texts', 'send_emails', 'send_letters']
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_another_service_with_manage_permissions(notify_api,
                                                                      notify_db,
                                                                      notify_db_session,
                                                                      sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            # they must exist in db first
            user_to_add = User(
                name='Invited User',
                email_address='invited@digital.cabinet-office.gov.uk',
                password='password',
                mobile_number='+4477123456'
            )
            save_model_user(user_to_add)

            data = {'permissions': ['manage_service']}
            auth_header = create_authorization_header(
                path='/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                request_body=json.dumps(data),
                method='POST'
            )

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_authorization_header(
                path=url_for('user.get_user', user_id=user_to_add.id),
                method='GET'
            )
            resp = client.get(url_for('user.get_user', user_id=user_to_add.id),
                              headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))

            permissions = json_resp['data']['permissions'][str(sample_service.id)]
            expected_permissions = ['manage_users', 'manage_settings', 'manage_templates']
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_another_service_with_manage_api_keys(notify_api,
                                                                   notify_db,
                                                                   notify_db_session,
                                                                   sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            # they must exist in db first
            user_to_add = User(
                name='Invited User',
                email_address='invited@digital.cabinet-office.gov.uk',
                password='password',
                mobile_number='+4477123456'
            )
            save_model_user(user_to_add)

            data = {'permissions': ['manage_api_keys']}
            auth_header = create_authorization_header(
                path='/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                request_body=json.dumps(data),
                method='POST'
            )

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_authorization_header(
                path=url_for('user.get_user', user_id=user_to_add.id),
                method='GET'
            )
            resp = client.get(url_for('user.get_user', user_id=user_to_add.id),
                              headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))

            permissions = json_resp['data']['permissions'][str(sample_service.id)]
            expected_permissions = ['manage_api_keys', 'access_developer_docs']
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_non_existing_service_returns404(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            user_to_add = User(
                name='Invited User',
                email_address='invited@digital.cabinet-office.gov.uk',
                password='password',
                mobile_number='+4477123456'
            )
            save_model_user(user_to_add)

            incorrect_id = uuid.uuid4()

            data = {'permissions': ['send_messages', 'manage_service', 'manage_api_keys']}
            auth_header = create_authorization_header(
                path='/service/{}/users/{}'.format(incorrect_id, user_to_add.id),
                request_body=json.dumps(data),
                method='POST'
            )

            resp = client.post(
                '/service/{}/users/{}'.format(incorrect_id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            result = json.loads(resp.get_data(as_text=True))
            expected_message = 'Service not found for id: {}'.format(incorrect_id)

            assert resp.status_code == 404
            assert result['result'] == 'error'
            assert result['message'] == expected_message


def test_add_existing_user_of_service_to_service_returns400(notify_api, notify_db, notify_db_session, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            existing_user_id = sample_service.users[0].id

            data = {'permissions': ['send_messages', 'manage_service', 'manage_api_keys']}
            auth_header = create_authorization_header(
                path='/service/{}/users/{}'.format(sample_service.id, existing_user_id),
                request_body=json.dumps(data),
                method='POST'
            )

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, existing_user_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            result = json.loads(resp.get_data(as_text=True))
            expected_message = 'User id: {} already part of service id: {}'.format(existing_user_id, sample_service.id)

            assert resp.status_code == 400
            assert result['result'] == 'error'
            assert result['message'] == expected_message


def test_add_unknown_user_to_service_returns404(notify_api, notify_db, notify_db_session, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            incorrect_id = 9876

            data = {'permissions': ['send_messages', 'manage_service', 'manage_api_keys']}
            auth_header = create_authorization_header(
                path='/service/{}/users/{}'.format(sample_service.id, incorrect_id),
                request_body=json.dumps(data),
                method='POST'
            )

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, incorrect_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            result = json.loads(resp.get_data(as_text=True))
            expected_message = 'User not found for id: {}'.format(incorrect_id)

            assert resp.status_code == 404
            assert result['result'] == 'error'
            assert result['message'] == expected_message
