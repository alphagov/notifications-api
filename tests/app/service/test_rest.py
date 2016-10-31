from datetime import datetime
import json
import uuid

import pytest
from flask import url_for
from freezegun import freeze_time

from app.dao.users_dao import save_model_user
from app.dao.services_dao import dao_remove_user_from_service
from app.models import User, Organisation
from tests import create_authorization_header
from tests.app.conftest import (
    sample_service as create_sample_service,
    sample_service_permission as create_sample_service_permission,
    sample_user as create_sample_user,
    sample_notification as create_sample_notification,
    sample_notification_with_job)
from app.models import KEY_TYPE_TEST


def test_get_service_list(notify_api, service_factory):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_factory.get('one', email_from='one')
            service_factory.get('two', email_from='two')
            service_factory.get('three', email_from='three')
            auth_header = create_authorization_header()
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
            service_factory.get('one', sample_user, email_from='one')
            service_factory.get('two', sample_user, email_from='two')
            service_factory.get('three', sample_user, email_from='three')

            auth_header = create_authorization_header()
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

            service_factory.get('one', sample_user, email_from='one')
            service_factory.get('two', sample_user, email_from='two')
            service_factory.get('three', sample_user, email_from='three')

            auth_header = create_authorization_header()
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
            auth_header = create_authorization_header()
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
            auth_header = create_authorization_header()
            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[auth_header]
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == sample_service.name
            assert json_resp['data']['id'] == str(sample_service.id)
            assert not json_resp['data']['research_mode']
            assert json_resp['data']['organisation'] is None
            assert json_resp['data']['branding'] == 'govuk'


def test_get_service_by_id_should_404_if_no_service(notify_api, notify_db):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_id = str(uuid.uuid4())
            auth_header = create_authorization_header()
            resp = client.get(
                '/service/{}'.format(service_id),
                headers=[auth_header]
            )
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'No result found'


def test_get_service_by_id_and_user(notify_api, service_factory, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service = service_factory.get('new service', sample_user, email_from='new.service')
            auth_header = create_authorization_header()
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
            auth_header = create_authorization_header()
            resp = client.get(
                '/service/{}?user_id={}'.format(service_id, sample_user.id),
                headers=[auth_header]
            )
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'No result found'


def test_create_service(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'created service',
                'user_id': str(sample_user.id),
                'message_limit': 1000,
                'restricted': False,
                'active': False,
                'email_from': 'created.service',
                'created_by': str(sample_user.id)}
            auth_header = create_authorization_header()
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
            assert not json_resp['data']['research_mode']

            auth_header_fetch = create_authorization_header()

            resp = client.get(
                '/service/{}?user_id={}'.format(json_resp['data']['id'], sample_user.id),
                headers=[auth_header_fetch]
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == 'created service'
            assert not json_resp['data']['research_mode']
            assert not json_resp['data']['can_send_letters']


def test_should_not_create_service_with_missing_user_id_field(notify_api, fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'email_from': 'service',
                'name': 'created service',
                'message_limit': 1000,
                'restricted': False,
                'active': False,
                'created_by': str(fake_uuid)
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['user_id']


def test_should_error_if_created_by_missing(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'email_from': 'service',
                'name': 'created service',
                'message_limit': 1000,
                'restricted': False,
                'active': False,
                'user_id': str(sample_user.id)
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['created_by']


def test_should_not_create_service_with_missing_if_user_id_is_not_in_database(notify_api,
                                                                              notify_db,
                                                                              notify_db_session,
                                                                              fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'email_from': 'service',
                'user_id': fake_uuid,
                'name': 'created service',
                'message_limit': 1000,
                'restricted': False,
                'active': False,
                'created_by': str(fake_uuid)
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 404
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'No result found'


def test_should_not_create_service_if_missing_data(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'user_id': str(sample_user.id)
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['name']
            assert 'Missing data for required field.' in json_resp['message']['message_limit']
            assert 'Missing data for required field.' in json_resp['message']['restricted']


def test_should_not_create_service_with_duplicate_name(notify_api,
                                                       sample_user,
                                                       sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': sample_service.name,
                'user_id': str(sample_service.users[0].id),
                'message_limit': 1000,
                'restricted': False,
                'active': False,
                'email_from': 'sample.service2',
                'created_by': str(sample_user.id)}
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert "Duplicate service name '{}'".format(sample_service.name) in json_resp['message']['name']


def test_create_service_should_throw_duplicate_key_constraint_for_existing_email_from(notify_api,
                                                                                      service_factory,
                                                                                      sample_user):
    first_service = service_factory.get('First service', email_from='first.service')
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_name = 'First SERVICE'
            data = {
                'name': service_name,
                'user_id': str(first_service.users[0].id),
                'message_limit': 1000,
                'restricted': False,
                'active': False,
                'email_from': 'first.service',
                'created_by': str(sample_user.id)}
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert "Duplicate service name '{}'".format(service_name) in json_resp['message']['name']


def test_update_service(notify_api, notify_db, sample_service):
    org = Organisation(colour='#000000', logo='justice-league.png', name='Justice League')
    notify_db.session.add(org)
    notify_db.session.commit()

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[auth_header]
            )
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert json_resp['data']['name'] == sample_service.name

            data = {
                'name': 'updated service name',
                'email_from': 'updated.service.name',
                'created_by': str(sample_service.created_by.id),
                'organisation': str(org.id)
            }

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}'.format(sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            result = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert result['data']['name'] == 'updated service name'
            assert result['data']['email_from'] == 'updated.service.name'
            assert result['data']['organisation'] == str(org.id)


def test_update_service_flags(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[auth_header]
            )
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert json_resp['data']['name'] == sample_service.name
            assert json_resp['data']['research_mode'] is False
            assert json_resp['data']['can_send_letters'] is False

            data = {
                'research_mode': True,
                'can_send_letters': True
            }

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}'.format(sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            result = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert result['data']['research_mode'] is True
            assert result['data']['can_send_letters'] is True


def test_update_service_research_mode_throws_validation_error(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[auth_header]
            )
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert json_resp['data']['name'] == sample_service.name
            assert not json_resp['data']['research_mode']

            data = {
                'research_mode': "dedede"
            }

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}'.format(sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            result = json.loads(resp.get_data(as_text=True))
            assert result['message']['research_mode'][0] == "Not a valid boolean."
            assert resp.status_code == 400


def test_should_not_update_service_with_duplicate_name(notify_api,
                                                       notify_db,
                                                       notify_db_session,
                                                       sample_user,
                                                       sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_name = "another name"
            service = create_sample_service(
                notify_db,
                notify_db_session,
                service_name=service_name,
                user=sample_user,
                email_from='another.name')
            data = {
                'name': service_name,
                'created_by': str(service.created_by.id)
            }

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}'.format(sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert "Duplicate service name '{}'".format(service_name) in json_resp['message']['name']


def test_should_not_update_service_with_duplicate_email_from(notify_api,
                                                             notify_db,
                                                             notify_db_session,
                                                             sample_user,
                                                             sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            email_from = "duplicate.name"
            service_name = "duplicate name"
            service = create_sample_service(
                notify_db,
                notify_db_session,
                service_name=service_name,
                user=sample_user,
                email_from=email_from)
            data = {
                'name': service_name,
                'email_from': email_from,
                'created_by': str(service.created_by.id)
            }

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}'.format(sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert (
                "Duplicate service name '{}'".format(service_name) in json_resp['message']['name'] or
                "Duplicate service name '{}'".format(email_from) in json_resp['message']['name']
            )


def test_update_service_should_404_if_id_is_invalid(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'updated service name'
            }

            missing_service_id = uuid.uuid4()

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}'.format(missing_service_id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert resp.status_code == 404


def test_get_users_by_service(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user_on_service = sample_service.users[0]
            auth_header = create_authorization_header()

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
                                                                                      sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            dao_remove_user_from_service(sample_service, sample_service.users[0])
            auth_header = create_authorization_header()

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
            auth_header = create_authorization_header()

            response = client.get(
                '/service/{}/users'.format(service_id),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert response.status_code == 404
            result = json.loads(response.get_data(as_text=True))
            assert result['result'] == 'error'
            assert result['message'] == 'No result found'


def test_default_permissions_are_added_for_user_service(notify_api,
                                                        notify_db,
                                                        notify_db_session,
                                                        sample_service,
                                                        sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'created service',
                'user_id': str(sample_user.id),
                'message_limit': 1000,
                'restricted': False,
                'active': False,
                'email_from': 'created.service',
                'created_by': str(sample_user.id)}
            auth_header = create_authorization_header()
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

            auth_header_fetch = create_authorization_header()

            resp = client.get(
                '/service/{}?user_id={}'.format(json_resp['data']['id'], sample_user.id),
                headers=[auth_header_fetch]
            )
            assert resp.status_code == 200
            header = create_authorization_header()
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
                                                                   sample_service,
                                                                   sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            # check which users part of service
            user_already_in_service = sample_service.users[0]
            auth_header = create_authorization_header()

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

            data = [{"permission": "send_emails"},
                    {"permission": "send_letters"},
                    {"permission": "send_texts"},
                    {"permission": "manage_users"},
                    {"permission": "manage_settings"},
                    {"permission": "manage_api_keys"},
                    {"permission": "manage_templates"},
                    {"permission": "view_activity"}]

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            assert resp.status_code == 201

            # check new user added to service
            auth_header = create_authorization_header()

            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header],
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert str(user_to_add.id) in json_resp['data']['users']

            # check user has all permissions
            auth_header = create_authorization_header()
            resp = client.get(url_for('user.get_user', user_id=user_to_add.id),
                              headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            permissions = json_resp['data']['permissions'][str(sample_service.id)]
            expected_permissions = ['send_texts', 'send_emails', 'send_letters', 'manage_users',
                                    'manage_settings', 'manage_templates', 'manage_api_keys', 'view_activity']
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_another_service_with_send_permissions(notify_api,
                                                                    notify_db,
                                                                    notify_db_session,
                                                                    sample_service,
                                                                    sample_user):
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

            data = [{"permission": "send_emails"},
                    {"permission": "send_letters"},
                    {"permission": "send_texts"}]

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_authorization_header()
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
                                                                      sample_service,
                                                                      sample_user):
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

            data = [{"permission": "manage_users"},
                    {"permission": "manage_settings"},
                    {"permission": "manage_templates"}]

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_authorization_header()
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
                                                                   sample_service,
                                                                   sample_user):
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

            data = [{"permission": "manage_api_keys"}]

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_authorization_header()
            resp = client.get(url_for('user.get_user', user_id=user_to_add.id),
                              headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))

            permissions = json_resp['data']['permissions'][str(sample_service.id)]
            expected_permissions = ['manage_api_keys']
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_non_existing_service_returns404(notify_api,
                                                              notify_db,
                                                              notify_db_session,
                                                              sample_user):
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
            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}/users/{}'.format(incorrect_id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            result = json.loads(resp.get_data(as_text=True))
            expected_message = 'No result found'

            assert resp.status_code == 404
            assert result['result'] == 'error'
            assert result['message'] == expected_message


def test_add_existing_user_of_service_to_service_returns400(notify_api, notify_db, notify_db_session, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            existing_user_id = sample_service.users[0].id

            data = {'permissions': ['send_messages', 'manage_service', 'manage_api_keys']}
            auth_header = create_authorization_header()

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
            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, incorrect_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            result = json.loads(resp.get_data(as_text=True))
            expected_message = 'No result found'

            assert resp.status_code == 404
            assert result['result'] == 'error'
            assert result['message'] == expected_message


def test_remove_user_from_service(notify_api, notify_db, notify_db_session, sample_service_permission):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            second_user = create_sample_user(
                notify_db,
                notify_db_session,
                email="new@digital.cabinet-office.gov.uk")
            # Simulates successfully adding a user to the service
            second_permission = create_sample_service_permission(
                notify_db,
                notify_db_session,
                user=second_user)
            endpoint = url_for(
                'service.remove_user_from_service',
                service_id=str(second_permission.service.id),
                user_id=str(second_permission.user.id))
            auth_header = create_authorization_header()
            resp = client.delete(
                endpoint,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204


def test_remove_user_from_service(notify_api, notify_db, notify_db_session, sample_service_permission):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            second_user = create_sample_user(
                notify_db,
                notify_db_session,
                email="new@digital.cabinet-office.gov.uk")
            endpoint = url_for(
                'service.remove_user_from_service',
                service_id=str(sample_service_permission.service.id),
                user_id=str(second_user.id))
            auth_header = create_authorization_header()
            resp = client.delete(
                endpoint,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 404


def test_cannot_remove_only_user_from_service(notify_api,
                                              notify_db,
                                              notify_db_session,
                                              sample_service_permission):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            endpoint = url_for(
                'service.remove_user_from_service',
                service_id=str(sample_service_permission.service.id),
                user_id=str(sample_service_permission.user.id))
            auth_header = create_authorization_header()
            resp = client.delete(
                endpoint,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            result = json.loads(resp.get_data(as_text=True))
            assert result['message'] == 'You cannot remove the only user for a service'


# This test is just here verify get_service_and_api_key_history that is a temp solution
# until proper ui is sorted out on admin app
def test_get_service_and_api_key_history(notify_api, notify_db, notify_db_session, sample_service):

    from tests.app.conftest import sample_api_key as create_sample_api_key
    api_key = create_sample_api_key(notify_db, notify_db_session, service=sample_service)

    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            auth_header = create_authorization_header()
            response = client.get(
                path='/service/{}/history'.format(sample_service.id),
                headers=[auth_header]
            )
            assert response.status_code == 200

            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['data']['service_history'][0]['id'] == str(sample_service.id)
            assert json_resp['data']['api_key_history'][0]['id'] == str(api_key.id)


def test_set_reply_to_email_for_service(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[auth_header]
            )
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert json_resp['data']['name'] == sample_service.name

            data = {
                'reply_to_email_address': 'reply_test@service.gov.uk',
            }

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}'.format(sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            result = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert result['data']['reply_to_email_address'] == 'reply_test@service.gov.uk'


def test_get_all_notifications_for_service_in_order(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        service_1 = create_sample_service(notify_db, notify_db_session, service_name="1", email_from='1')
        service_2 = create_sample_service(notify_db, notify_db_session, service_name="2", email_from='2')

        create_sample_notification(notify_db, notify_db_session, service=service_2)

        notification_1 = create_sample_notification(notify_db, notify_db_session, service=service_1)
        notification_2 = create_sample_notification(notify_db, notify_db_session, service=service_1)
        notification_3 = create_sample_notification(notify_db, notify_db_session, service=service_1)

        auth_header = create_authorization_header()

        response = client.get(
            path='/service/{}/notifications'.format(service_1.id),
            headers=[auth_header])

        resp = json.loads(response.get_data(as_text=True))
        assert len(resp['notifications']) == 3
        assert resp['notifications'][0]['to'] == notification_3.to
        assert resp['notifications'][1]['to'] == notification_2.to
        assert resp['notifications'][2]['to'] == notification_1.to
        assert response.status_code == 200


@pytest.mark.parametrize(
    'include_from_test_key, expected_count_of_notifications',
    [
        (False, 2),
        (True, 3)
    ]
)
def test_get_all_notifications_for_service_including_ones_made_by_jobs(
    client,
    notify_db,
    notify_db_session,
    sample_service,
    include_from_test_key,
    expected_count_of_notifications
):
    with_job = sample_notification_with_job(notify_db, notify_db_session, service=sample_service)
    without_job = create_sample_notification(notify_db, notify_db_session, service=sample_service)
    from_test_api_key = create_sample_notification(
        notify_db, notify_db_session, service=sample_service, key_type=KEY_TYPE_TEST
    )

    auth_header = create_authorization_header()

    response = client.get(
        path='/service/{}/notifications?include_from_test_key={}'.format(
            sample_service.id, include_from_test_key
        ),
        headers=[auth_header]
    )

    resp = json.loads(response.get_data(as_text=True))
    assert len(resp['notifications']) == expected_count_of_notifications
    assert resp['notifications'][0]['to'] == with_job.to
    assert resp['notifications'][1]['to'] == without_job.to
    assert response.status_code == 200


def test_get_only_api_created_notifications_for_service(
    client,
    notify_db,
    notify_db_session,
    sample_service
):
    with_job = sample_notification_with_job(notify_db, notify_db_session, service=sample_service)
    without_job = create_sample_notification(notify_db, notify_db_session, service=sample_service)

    auth_header = create_authorization_header()

    response = client.get(
        path='/service/{}/notifications?include_jobs=false'.format(sample_service.id),
        headers=[auth_header])

    resp = json.loads(response.get_data(as_text=True))
    assert len(resp['notifications']) == 1
    assert resp['notifications'][0]['id'] == str(without_job.id)
    assert response.status_code == 200


def test_set_sms_sender_for_service(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[auth_header]
            )
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert json_resp['data']['name'] == sample_service.name

            data = {
                'sms_sender': 'elevenchars',
            }

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}'.format(sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            result = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert result['data']['sms_sender'] == 'elevenchars'


def test_set_sms_sender_for_service_rejects_invalid_characters(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[auth_header]
            )
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert json_resp['data']['name'] == sample_service.name

            data = {
                'sms_sender': 'invalid####',
            }

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}'.format(sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            result = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 400
            assert result['result'] == 'error'
            assert result['message'] == {'sms_sender': ['Only alphanumeric characters allowed']}


@pytest.mark.parametrize('today_only,stats', [
    ('False', {
        'requested': 2,
        'delivered': 1,
        'failed': 0
    }),
    ('True', {
        'requested': 1,
        'delivered': 0,
        'failed': 0
    })
], ids=['seven_days', 'today'])
def test_get_detailed_service(notify_db, notify_db_session, notify_api, sample_service, today_only, stats):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        with freeze_time('2000-01-01T12:00:00'):
            create_sample_notification(notify_db, notify_db_session, status='delivered')
        with freeze_time('2000-01-02T12:00:00'):
            create_sample_notification(notify_db, notify_db_session, status='created')
            resp = client.get(
                '/service/{}?detailed=True&today_only={}'.format(sample_service.id, today_only),
                headers=[create_authorization_header()]
            )

    assert resp.status_code == 200
    service = json.loads(resp.get_data(as_text=True))['data']
    assert service['id'] == str(sample_service.id)
    assert 'statistics' in service.keys()
    assert set(service['statistics'].keys()) == set(['sms', 'email'])
    assert service['statistics']['sms'] == stats


def test_get_weekly_notification_stats(notify_api, notify_db, notify_db_session):
    with freeze_time('2000-01-01T12:00:00'):
        noti = create_sample_notification(notify_db, notify_db_session)
    with notify_api.test_request_context(), notify_api.test_client() as client, freeze_time('2000-01-02T12:00:00'):
        resp = client.get(
            '/service/{}/notifications/weekly'.format(noti.service_id),
            headers=[create_authorization_header()]
        )

    assert resp.status_code == 200
    data = json.loads(resp.get_data(as_text=True))['data']
    assert data == {
        '1999-12-27': {
            'sms': {
                'requested': 1,
                'delivered': 0,
                'failed': 0
            },
            'email': {
                'requested': 0,
                'delivered': 0,
                'failed': 0
            }
        }
    }


def test_get_services_with_detailed_flag(notify_api, notify_db, notify_db_session):
    notifications = [
        create_sample_notification(notify_db, notify_db_session),
        create_sample_notification(notify_db, notify_db_session)
    ]
    with notify_api.test_request_context(), notify_api.test_client() as client:
        resp = client.get(
            '/service?detailed=True',
            headers=[create_authorization_header()]
        )

    assert resp.status_code == 200
    data = json.loads(resp.get_data(as_text=True))['data']
    assert len(data) == 1
    assert data[0]['name'] == 'Sample service'
    assert data[0]['id'] == str(notifications[0].service_id)
    assert data[0]['statistics'] == {
        'email': {'delivered': 0, 'failed': 0, 'requested': 0},
        'sms': {'delivered': 0, 'failed': 0, 'requested': 2}
    }


def test_get_detailed_services_groups_by_service(notify_db, notify_db_session):
    from app.service.rest import get_detailed_services

    service_1 = create_sample_service(notify_db, notify_db_session, service_name="1", email_from='1')
    service_2 = create_sample_service(notify_db, notify_db_session, service_name="2", email_from='2')

    create_sample_notification(notify_db, notify_db_session, service=service_1, status='created')
    create_sample_notification(notify_db, notify_db_session, service=service_2, status='created')
    create_sample_notification(notify_db, notify_db_session, service=service_1, status='delivered')
    create_sample_notification(notify_db, notify_db_session, service=service_1, status='created')

    data = get_detailed_services()
    data = sorted(data, key=lambda x: x['name'])

    assert len(data) == 2
    assert data[0]['id'] == str(service_1.id)
    assert data[0]['statistics'] == {
        'email': {'delivered': 0, 'failed': 0, 'requested': 0},
        'sms': {'delivered': 1, 'failed': 0, 'requested': 3}
    }
    assert data[1]['id'] == str(service_2.id)
    assert data[1]['statistics'] == {
        'email': {'delivered': 0, 'failed': 0, 'requested': 0},
        'sms': {'delivered': 0, 'failed': 0, 'requested': 1}
    }


def test_get_detailed_services_includes_services_with_no_notifications(notify_db, notify_db_session):
    from app.service.rest import get_detailed_services

    service_1 = create_sample_service(notify_db, notify_db_session, service_name="1", email_from='1')
    service_2 = create_sample_service(notify_db, notify_db_session, service_name="2", email_from='2')

    create_sample_notification(notify_db, notify_db_session, service=service_1)

    data = get_detailed_services()
    data = sorted(data, key=lambda x: x['name'])

    assert len(data) == 2
    assert data[0]['id'] == str(service_1.id)
    assert data[0]['statistics'] == {
        'email': {'delivered': 0, 'failed': 0, 'requested': 0},
        'sms': {'delivered': 0, 'failed': 0, 'requested': 1}
    }
    assert data[1]['id'] == str(service_2.id)
    assert data[1]['statistics'] == {
        'email': {'delivered': 0, 'failed': 0, 'requested': 0},
        'sms': {'delivered': 0, 'failed': 0, 'requested': 0}
    }


def test_get_detailed_services_only_includes_todays_notifications(notify_db, notify_db_session):
    from app.service.rest import get_detailed_services

    create_sample_notification(notify_db, notify_db_session, created_at=datetime(2015, 10, 9, 23, 59))
    create_sample_notification(notify_db, notify_db_session, created_at=datetime(2015, 10, 10, 0, 0))
    create_sample_notification(notify_db, notify_db_session, created_at=datetime(2015, 10, 10, 12, 0))

    with freeze_time('2015-10-10T12:00:00'):
        data = get_detailed_services()
        data = sorted(data, key=lambda x: x['id'])

    assert len(data) == 1
    assert data[0]['statistics'] == {
        'email': {'delivered': 0, 'failed': 0, 'requested': 0},
        'sms': {'delivered': 0, 'failed': 0, 'requested': 2}
    }


@freeze_time('2012-12-12T12:00:01')
def test_get_notification_billable_unit_count(client, notify_db, notify_db_session):
    notification = create_sample_notification(notify_db, notify_db_session)
    response = client.get(
        '/service/{}/billable-units?year=2012'.format(notification.service_id),
        headers=[create_authorization_header(service_id=notification.service_id)]
    )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {
        'December': 1
    }


def test_get_notification_billable_unit_count_missing_year(client, sample_service):
    response = client.get(
        '/service/{}/billable-units'.format(sample_service.id),
        headers=[create_authorization_header(service_id=sample_service.id)]
    )
    assert response.status_code == 400
    assert json.loads(response.get_data(as_text=True)) == {
        'message': 'No valid year provided', 'result': 'error'
    }
